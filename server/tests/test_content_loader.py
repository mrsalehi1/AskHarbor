import json
from pathlib import Path

import pytest

from app.config import DEFAULT_CONTENT_DIR
from app.content import ContentLoadError, load_content_directory


def bot_document(bot_id: str, **overrides: object) -> dict:
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
        "answers": [{"id": "start", "label": "Start?", "answer": "Go."}],
    }
    document.update(overrides)
    return document


def write(directory: Path, name: str, document: object) -> Path:
    path = directory / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_loads_one_bot_per_file_keyed_by_config_id(tmp_path: Path) -> None:
    write(tmp_path, "first-file.json", bot_document("alpha"))
    write(tmp_path, "second-file.json", bot_document("beta"))

    bots = load_content_directory(tmp_path)

    assert sorted(bots) == ["alpha", "beta"]
    assert bots["alpha"].config.name == "alpha bot"


def test_ignores_files_that_are_not_json_and_subdirectories(tmp_path: Path) -> None:
    write(tmp_path, "alpha.json", bot_document("alpha"))
    (tmp_path / "notes.txt").write_text("not content")
    (tmp_path / "nested").mkdir()
    write(tmp_path / "nested", "beta.json", bot_document("beta"))

    assert sorted(load_content_directory(tmp_path)) == ["alpha"]


def test_same_bot_id_in_two_files_is_rejected_naming_both(tmp_path: Path) -> None:
    write(tmp_path, "a.json", bot_document("shop"))
    write(tmp_path, "b.json", bot_document("shop"))

    with pytest.raises(ContentLoadError) as excinfo:
        load_content_directory(tmp_path)

    [report] = excinfo.value.reports
    assert report.path.name == "b.json"
    assert report.problems[0].path == "config.id"
    assert "already defined in a.json" in report.problems[0].message


def test_one_bad_file_rejects_the_whole_directory(tmp_path: Path) -> None:
    write(tmp_path, "good.json", bot_document("good"))
    bad = bot_document("bad")
    bad["config"]["primary_color"] = "red"
    write(tmp_path, "bad.json", bad)

    with pytest.raises(ContentLoadError) as excinfo:
        load_content_directory(tmp_path)

    assert [report.path.name for report in excinfo.value.reports] == ["bad.json"]


def test_problems_from_every_file_are_reported_together(tmp_path: Path) -> None:
    first = bot_document("first")
    first["answers"][0]["label"] = ""
    write(tmp_path, "first.json", first)
    (tmp_path / "second.json").write_text("{ not json", encoding="utf-8")
    third = bot_document("third")
    third["config"]["opening_option_ids"] = ["missing"]
    write(tmp_path, "third.json", third)

    with pytest.raises(ContentLoadError) as excinfo:
        load_content_directory(tmp_path)

    message = str(excinfo.value)
    assert message.startswith("Bot content was rejected (3 files with problems):")
    assert "first.json" in message and "answers[0].label: text must not be blank" in message
    assert "second.json" in message and "(document): malformed JSON" in message
    assert "third.json" in message
    assert "opening option 'missing' has no matching answer" in message


def test_missing_directory_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ContentLoadError, match="does not exist"):
        load_content_directory(tmp_path / "nowhere")


def test_directory_without_json_files_is_a_clear_error(tmp_path: Path) -> None:
    (tmp_path / "readme.txt").write_text("nothing here")
    with pytest.raises(ContentLoadError, match="no .json files"):
        load_content_directory(tmp_path)


def test_file_that_is_not_utf8_is_reported(tmp_path: Path) -> None:
    (tmp_path / "latin.json").write_bytes(b'{"format_version": 1, "x": "\xe9"}')
    with pytest.raises(ContentLoadError, match="not UTF-8"):
        load_content_directory(tmp_path)


def test_shipped_content_directory_loads_the_demo_and_library_bots() -> None:
    bots = load_content_directory(DEFAULT_CONTENT_DIR)

    assert sorted(bots) == ["demo", "library"]
    demo = bots["demo"]
    assert demo.config.name == "AskHarbor"
    assert [option.id for option in demo.config.options] == [
        "getting-started",
        "features",
        "contact",
    ]
    assert demo.answers["getting-started"].next_option_ids == ["installation", "customize"]
    library = bots["library"]
    assert library.config.primary_color == "#0f766e"
    assert len(library.config.options) == 4
