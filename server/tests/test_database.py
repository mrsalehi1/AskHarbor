"""Database layer tests against a real PostgreSQL.

These run only when ASKHARBOR_TEST_DATABASE_URL points at a disposable
PostgreSQL database (see "PostgreSQL storage" in README.md). The schema is
migrated once per test run with Alembic — the same path a deployment uses —
and every table is truncated between tests.
"""

import importlib
import json

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from conftest import ALEMBIC_DIR, SERVER_DIR, TEST_URL, requires_database
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app import config, main
from app.content import (
    ContentLoadError,
    InvalidBotContent,
    definition_from_document,
    load_content_documents,
)
from app.orm import Base, BotContent, Website
from app.storage import (
    DatabaseContentSource,
    RevisionConflict,
    assert_database_ready,
    get_bot_document,
    import_documents,
    save_bot_document,
)

CONTENT_DIR = SERVER_DIR / "content"

pytestmark = requires_database


def test_migrated_schema_matches_the_orm_models(engine) -> None:
    """The migration and the ORM must describe the same tables."""
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diff = compare_metadata(context, Base.metadata)
    assert diff == [], f"schema drift between alembic and app.orm: {diff}"


# --- import ------------------------------------------------------------------


def test_fresh_import_creates_websites_and_documents(session) -> None:
    report = import_documents(session, CONTENT_DIR)
    session.commit()

    assert report.imported == ["demo", "library"]
    assert report.replaced == [] and report.skipped == []
    websites = session.execute(select(Website).order_by(Website.slug)).scalars().all()
    assert [(w.slug, w.name) for w in websites] == [
        ("demo", "AskHarbor"),
        ("library", "Harbor Library"),
    ]
    stored = get_bot_document(session, "demo")
    assert stored is not None
    document, revision = stored
    assert revision == 1
    assert document == json.loads((CONTENT_DIR / "demo.json").read_text())


def test_second_import_skips_existing_ids(session) -> None:
    import_documents(session, CONTENT_DIR)
    session.commit()

    report = import_documents(session, CONTENT_DIR)
    session.commit()

    assert report.skipped == ["demo", "library"]
    assert report.imported == [] and report.replaced == []
    assert get_bot_document(session, "demo")[1] == 1


def test_replace_overwrites_and_bumps_the_revision(session, tmp_path) -> None:
    import_documents(session, CONTENT_DIR)
    session.commit()
    changed = json.loads((CONTENT_DIR / "demo.json").read_text())
    changed["config"]["greeting"] = "A replaced greeting."
    (tmp_path / "demo.json").write_text(json.dumps(changed))

    report = import_documents(session, tmp_path, replace=True)
    session.commit()

    assert report.replaced == ["demo"]
    document, revision = get_bot_document(session, "demo")
    assert revision == 2
    assert document["config"]["greeting"] == "A replaced greeting."
    # The other bot was not touched.
    assert get_bot_document(session, "library")[1] == 1


def test_invalid_batch_imports_nothing(session, tmp_path) -> None:
    (tmp_path / "good.json").write_text((CONTENT_DIR / "demo.json").read_text())
    (tmp_path / "bad.json").write_text('{"format_version": 1')

    with pytest.raises(ContentLoadError, match="bad.json"):
        import_documents(session, tmp_path)
    session.rollback()

    assert session.execute(select(Website)).first() is None
    assert session.execute(select(BotContent)).first() is None


def test_import_command_commits_in_one_transaction(
    session, engine, tmp_path, capsys, monkeypatch
) -> None:
    """The CLI module wraps the import in a single transaction."""
    from app import import_content

    monkeypatch.setenv("ASKHARBOR_DATABASE_URL", TEST_URL)
    config.get_settings.cache_clear()
    try:
        exit_code = import_content.main([str(CONTENT_DIR)])
    finally:
        config.get_settings.cache_clear()

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "imported 2 (demo, library)" in out
    with engine.connect() as connection:
        count = connection.execute(text("SELECT count(*) FROM bot_contents")).scalar()
    assert count == 2


def test_import_command_reports_invalid_content(tmp_path, capsys, monkeypatch) -> None:
    from app import import_content

    (tmp_path / "bad.json").write_text('{"format_version": 7}')
    monkeypatch.setenv("ASKHARBOR_DATABASE_URL", TEST_URL)
    config.get_settings.cache_clear()
    try:
        exit_code = import_content.main([str(tmp_path)])
    finally:
        config.get_settings.cache_clear()

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "Nothing was imported." in err
    assert "unsupported format_version 7" in err


# --- revision guarded saves ----------------------------------------------------


def demo_document() -> dict:
    return json.loads((CONTENT_DIR / "demo.json").read_text())


def test_save_with_the_current_revision_succeeds(session) -> None:
    import_documents(session, CONTENT_DIR)
    session.commit()
    changed = demo_document()
    changed["config"]["name"] = "Saved name"

    new_revision = save_bot_document(session, "demo", changed, expected_revision=1)
    session.commit()

    assert new_revision == 2
    document, revision = get_bot_document(session, "demo")
    assert revision == 2
    assert document["config"]["name"] == "Saved name"


def test_save_with_a_stale_revision_conflicts_and_writes_nothing(session) -> None:
    import_documents(session, CONTENT_DIR)
    session.commit()
    first = demo_document()
    first["config"]["name"] = "First save"
    save_bot_document(session, "demo", first, expected_revision=1)
    session.commit()

    second = demo_document()
    second["config"]["name"] = "Second save from a stale copy"
    with pytest.raises(RevisionConflict) as excinfo:
        save_bot_document(session, "demo", second, expected_revision=1)
    session.rollback()

    assert excinfo.value.current_revision == 2
    assert "revision 2, not 1" in str(excinfo.value)
    document, revision = get_bot_document(session, "demo")
    assert revision == 2
    assert document["config"]["name"] == "First save"


def test_save_rejects_invalid_documents_before_touching_the_database(session) -> None:
    import_documents(session, CONTENT_DIR)
    session.commit()
    broken = demo_document()
    broken["config"]["primary_color"] = "red"

    with pytest.raises(InvalidBotContent, match="hex color"):
        save_bot_document(session, "demo", broken, expected_revision=1)
    session.rollback()

    assert get_bot_document(session, "demo")[1] == 1


def test_save_to_an_unknown_website_is_a_lookup_error(session) -> None:
    with pytest.raises(LookupError, match="nowhere"):
        save_bot_document(session, "nowhere", demo_document(), expected_revision=1)


# --- the content source the public API uses ------------------------------------


def test_database_source_serves_the_same_definitions_as_the_files(session, engine) -> None:
    import_documents(session, CONTENT_DIR)
    session.commit()
    from sqlalchemy.orm import sessionmaker

    source = DatabaseContentSource(sessionmaker(bind=engine))
    file_documents = load_content_documents(CONTENT_DIR)

    assert source.ids() == sorted(file_documents)
    for slug, document in file_documents.items():
        assert source.get(slug) == definition_from_document(document)
    assert source.get("missing") is None


def test_database_source_sees_a_save_immediately(session, engine) -> None:
    import_documents(session, CONTENT_DIR)
    session.commit()
    from sqlalchemy.orm import sessionmaker

    source = DatabaseContentSource(sessionmaker(bind=engine))
    assert source.get("demo").config.name == "AskHarbor"

    changed = demo_document()
    changed["config"]["name"] = "Renamed live"
    save_bot_document(session, "demo", changed, expected_revision=1)
    session.commit()

    assert source.get("demo").config.name == "Renamed live"


def test_api_responses_are_identical_in_file_and_database_mode(session, monkeypatch) -> None:
    import_documents(session, CONTENT_DIR)
    session.commit()

    file_client = TestClient(main.app)
    file_config = file_client.get("/api/v1/bots/demo").json()
    file_message = file_client.post(
        "/api/v1/bots/demo/messages", json={"option_id": "getting-started"}
    ).json()

    monkeypatch.setenv("ASKHARBOR_CONTENT_SOURCE", "database")
    monkeypatch.setenv("ASKHARBOR_DATABASE_URL", TEST_URL)
    config.get_settings.cache_clear()
    module = importlib.reload(main)
    try:
        db_client = TestClient(module.app)
        assert db_client.get("/api/v1/bots/demo").json() == file_config
        assert (
            db_client.post(
                "/api/v1/bots/demo/messages", json={"option_id": "getting-started"}
            ).json()
            == file_message
        )
        assert db_client.get("/api/v1/bots/missing").status_code == 404
        assert (
            db_client.post("/api/v1/bots/demo/messages", json={"option_id": "nope"}).status_code
            == 400
        )
    finally:
        monkeypatch.delenv("ASKHARBOR_CONTENT_SOURCE")
        monkeypatch.delenv("ASKHARBOR_DATABASE_URL")
        config.get_settings.cache_clear()
        importlib.reload(main)


def test_unmigrated_database_refuses_to_start(engine) -> None:
    autocommit = engine.execution_options(isolation_level="AUTOCOMMIT")
    empty_url = TEST_URL.rsplit("/", 1)[0] + "/askharbor_test_empty"
    with autocommit.connect() as connection:
        connection.execute(text("DROP DATABASE IF EXISTS askharbor_test_empty"))
        connection.execute(text("CREATE DATABASE askharbor_test_empty"))
    empty_engine = create_engine(empty_url)
    try:
        with pytest.raises(SystemExit, match="alembic upgrade head"):
            assert_database_ready(empty_engine, ALEMBIC_DIR)
    finally:
        empty_engine.dispose()
        with autocommit.connect() as connection:
            connection.execute(text("DROP DATABASE askharbor_test_empty"))


def test_migrated_database_passes_the_readiness_check(engine) -> None:
    assert_database_ready(engine, ALEMBIC_DIR)
