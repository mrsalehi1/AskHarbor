"""Reloading bot content swaps the whole set, or keeps what is already loaded."""

import asyncio
import json
import logging
import os
import signal
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


def write_bot(directory: Path, bot_id: str, answer: str = "Go.") -> None:
    document = {
        "format_version": 1,
        "config": {
            "id": bot_id,
            "name": f"{bot_id} bot",
            "greeting": "Hello",
            "launcher_label": "Open",
            "primary_color": "#123456",
            "opening_option_ids": ["start"],
        },
        "answers": [{"id": "start", "label": "Start?", "answer": answer}],
    }
    (directory / f"{bot_id}.json").write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture
def content_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the running app at a temporary content directory, restoring the bots after."""
    loaded_before = {bot_id: main.repository.get(bot_id) for bot_id in main.repository.ids()}
    monkeypatch.setattr(main.settings, "content_dir", tmp_path)
    try:
        yield tmp_path
    finally:
        main.repository.replace(loaded_before)


def test_valid_reload_replaces_the_whole_set(content_dir: Path) -> None:
    assert client.get("/api/v1/bots/demo").status_code == 200
    write_bot(content_dir, "fresh")

    assert main.reload_content() is True

    assert main.repository.ids() == ["fresh"]
    assert client.get("/api/v1/bots/fresh").status_code == 200
    assert client.get("/api/v1/bots/demo").status_code == 404


def test_reload_picks_up_edited_answers(content_dir: Path) -> None:
    write_bot(content_dir, "shop", answer="Old answer.")
    main.reload_content()
    write_bot(content_dir, "shop", answer="New answer.")

    main.reload_content()

    response = client.post("/api/v1/bots/shop/messages", json={"option_id": "start"})
    assert response.json()["answer"] == "New answer."


def test_invalid_reload_keeps_the_loaded_content_and_logs_the_problems(
    content_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (content_dir / "broken.json").write_text('{"format_version": 1', encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="askharbor"):
        assert main.reload_content() is False

    assert main.repository.ids() == ["demo", "library"]
    assert client.get("/api/v1/bots/demo").status_code == 200
    assert client.get("/api/v1/bots/library").status_code == 200
    message = caplog.records[-1].getMessage()
    assert "keeping the 2 bot(s) already loaded (demo, library)" in message
    assert "broken.json" in message
    assert "malformed JSON" in message


def test_one_bad_file_in_the_batch_keeps_everything_as_it_was(content_dir: Path) -> None:
    write_bot(content_dir, "good")
    bad = content_dir / "bad.json"
    bad.write_text(json.dumps({"format_version": 7}), encoding="utf-8")

    assert main.reload_content() is False

    assert main.repository.ids() == ["demo", "library"]
    assert client.get("/api/v1/bots/good").status_code == 404


def test_missing_directory_on_reload_keeps_the_loaded_content(
    content_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main.settings, "content_dir", content_dir / "gone")

    assert main.reload_content() is False
    assert main.repository.ids() == ["demo", "library"]


def test_startup_with_invalid_content_stops_with_the_problems(
    content_dir: Path,
) -> None:
    broken = {"format_version": 1, "config": {}, "answers": []}
    (content_dir / "broken.json").write_text(json.dumps(broken), encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main._load_startup_content()

    message = str(excinfo.value)
    assert "cannot start" in message
    assert "ASKHARBOR_CONTENT_DIR" in message
    assert "broken.json" in message
    assert "config.id: field is required" in message
    assert "answers: must have at least 1 item(s)" in message


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="SIGHUP is not available here")
def test_sighup_triggers_a_reload_on_the_event_loop(content_dir: Path) -> None:
    write_bot(content_dir, "signalled")
    loop = asyncio.new_event_loop()
    remove_handler = main.install_reload_signal(loop)
    try:
        os.kill(os.getpid(), signal.SIGHUP)
        loop.run_until_complete(asyncio.sleep(0.1))
    finally:
        remove_handler()
        loop.close()

    assert main.repository.ids() == ["signalled"]


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="SIGHUP is not available here")
def test_signal_handler_is_removed_on_shutdown(content_dir: Path) -> None:
    loop = asyncio.new_event_loop()
    remove_handler = main.install_reload_signal(loop)
    remove_handler()
    loop.close()

    assert signal.getsignal(signal.SIGHUP) is signal.SIG_DFL


def test_signal_install_outside_the_main_thread_degrades_to_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    outcome: dict[str, object] = {}

    def run() -> None:
        loop = asyncio.new_event_loop()
        try:
            outcome["remove"] = main.install_reload_signal(loop)
        finally:
            loop.close()

    with caplog.at_level(logging.WARNING, logger="askharbor"):
        thread = threading.Thread(target=run)
        thread.start()
        thread.join()

    assert callable(outcome["remove"])
    outcome["remove"]()  # must be a harmless no-op
    assert any("reload signal" in record.getMessage() for record in caplog.records)


def test_app_lifespan_runs_without_a_main_thread_loop() -> None:
    # TestClient drives the lifespan from a worker thread, where signal handlers
    # cannot be installed. The server must still start and serve requests.
    with TestClient(main.app) as started:
        assert started.get("/health").status_code == 200
        assert started.get("/api/v1/bots/library").status_code == 200
