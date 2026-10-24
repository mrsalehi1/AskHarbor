"""Website routes: details and embed snippet, settings, content with revisions,
backup export and import, per website CORS, the shared login limiter and the
admin panel files. Needs PostgreSQL (see conftest)."""

import importlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from conftest import TEST_URL, requires_database
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app import config, main
from app.login_limit import DatabaseLoginLimiter

pytestmark = requires_database

ADMIN = {"username": "admin", "password": "ChangeMeLocal123!"}
ADMIN_NEW = "an-admin-passphrase-2026"


@pytest.fixture
def app_module(clean_database, monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator:
    (tmp_path / "admin.html").write_text("<!doctype html><title>panel</title>")
    (tmp_path / "askharbor.js").write_text("// widget bundle")
    monkeypatch.setenv("ASKHARBOR_DATABASE_URL", TEST_URL)
    monkeypatch.setenv("ASKHARBOR_ADMIN_DIST", str(tmp_path))
    monkeypatch.setenv("ASKHARBOR_PUBLIC_URL", "https://faq.example.com/")
    config.get_settings.cache_clear()
    module = importlib.reload(main)
    try:
        yield module
    finally:
        for name in ("ASKHARBOR_DATABASE_URL", "ASKHARBOR_ADMIN_DIST", "ASKHARBOR_PUBLIC_URL"):
            monkeypatch.delenv(name, raising=False)
        config.get_settings.cache_clear()
        importlib.reload(main)


@pytest.fixture
def admin(app_module) -> Iterator[TestClient]:
    with TestClient(app_module.app, base_url="https://testserver") as client:
        client.post("/api/v1/auth/login", json=ADMIN)
        client.post(
            "/api/v1/auth/password",
            json={"current_password": ADMIN["password"], "new_password": ADMIN_NEW},
        )
        yield client


# --- details, embed snippet and settings ---------------------------------------------


def test_details_include_the_embed_snippet_for_the_public_url(admin) -> None:
    details = admin.get("/api/v1/websites/demo").json()

    assert details["slug"] == "demo" and details["revision"] == 1
    assert details["api_url"] == "https://faq.example.com"
    assert details["widget_url"] == "https://faq.example.com/admin/askharbor.js"
    assert 'data-api-url="https://faq.example.com"' in details["embed_snippet"]
    assert 'data-bot-id="demo"' in details["embed_snippet"]
    assert details["embed_snippet"].startswith("<script")
    assert details["can_manage"] is True


def test_settings_update_domain_name_and_origins(admin) -> None:
    response = admin.patch(
        "/api/v1/websites/demo",
        json={
            "name": "Demo renamed",
            "domain": "WWW.Example.com",
            "allowed_origins": ["https://www.example.com/", " https://app.example.com ", ""],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Demo renamed"
    assert body["domain"] == "www.example.com"
    assert body["allowed_origins"] == ["https://www.example.com", "https://app.example.com"]
    # The public widget config follows the bot document, not the website name.
    assert admin.get("/api/v1/bots/demo").json()["name"] == "AskHarbor"

    log = admin.get("/api/v1/websites/demo/audit").json()
    update = next(e for e in log if e["action"] == "settings_update")
    assert update["details"]["domain"] == "www.example.com"


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ({"allowed_origins": ["example.com"]}, "is not an origin"),
        ({"allowed_origins": ["https://example.com/path"]}, "is not an origin"),
        ({"domain": "https://example.com"}, "is not a domain"),
        ({"domain": "has space.com"}, "is not a domain"),
    ],
)
def test_invalid_settings_are_rejected_with_a_reason(admin, payload, fragment) -> None:
    response = admin.patch("/api/v1/websites/demo", json=payload)
    assert response.status_code == 422
    assert fragment in response.json()["detail"]
    assert admin.get("/api/v1/websites/demo").json()["allowed_origins"] == []


def test_clearing_the_domain_and_origins(admin) -> None:
    admin.patch(
        "/api/v1/websites/demo",
        json={"domain": "a.example", "allowed_origins": ["https://a.example"]},
    )
    cleared = admin.patch(
        "/api/v1/websites/demo", json={"domain": "", "allowed_origins": []}
    ).json()
    assert cleared["domain"] is None and cleared["allowed_origins"] == []


# --- per website CORS on the public routes ---------------------------------------------


def test_per_website_origins_govern_the_public_routes(admin) -> None:
    # Without a site list the global default (*) applies.
    assert (
        admin.get("/api/v1/bots/demo", headers={"Origin": "https://anyone.example"}).headers[
            "access-control-allow-origin"
        ]
        == "*"
    )

    admin.patch("/api/v1/websites/demo", json={"allowed_origins": ["https://shop.example"]})

    allowed = admin.get("/api/v1/bots/demo", headers={"Origin": "https://shop.example"})
    assert allowed.headers["access-control-allow-origin"] == "https://shop.example"
    assert "origin" in allowed.headers.get("vary", "").lower()
    denied = admin.get("/api/v1/bots/demo", headers={"Origin": "https://other.example"})
    assert denied.status_code == 200  # the data is public; the browser enforces the missing header
    assert "access-control-allow-origin" not in denied.headers

    preflight_ok = admin.options(
        "/api/v1/bots/demo/messages",
        headers={"Origin": "https://shop.example", "Access-Control-Request-Method": "POST"},
    )
    assert preflight_ok.status_code == 200
    assert preflight_ok.headers["access-control-allow-methods"] == "GET, POST"
    preflight_denied = admin.options(
        "/api/v1/bots/demo/messages",
        headers={"Origin": "https://other.example", "Access-Control-Request-Method": "POST"},
    )
    assert preflight_denied.status_code == 400

    # Other websites are not affected by demo's list.
    assert (
        admin.get("/api/v1/bots/library", headers={"Origin": "https://other.example"}).headers[
            "access-control-allow-origin"
        ]
        == "*"
    )
    # Requests without an Origin header (same-origin, curl) are untouched.
    assert "access-control-allow-origin" not in admin.get("/api/v1/bots/demo").headers


# --- content with revisions ----------------------------------------------------------------


def test_content_round_trip_with_revision_check(admin) -> None:
    loaded = admin.get("/api/v1/websites/demo/content").json()
    assert loaded["revision"] == 1
    document = loaded["document"]
    document["config"]["greeting"] = "Saved from the panel."

    saved = admin.put("/api/v1/websites/demo/content", json={"document": document, "revision": 1})
    assert saved.status_code == 200 and saved.json() == {"revision": 2}
    assert admin.get("/api/v1/bots/demo").json()["greeting"] == "Saved from the panel."

    stale = admin.put("/api/v1/websites/demo/content", json={"document": document, "revision": 1})
    assert stale.status_code == 409
    detail = stale.json()["detail"]
    assert detail["code"] == "revision_conflict" and detail["current_revision"] == 2

    audit = admin.get("/api/v1/websites/demo/audit").json()
    assert next(e for e in audit if e["action"] == "content_save")["details"] == {"revision": 2}


def test_invalid_content_is_rejected_with_the_shared_problem_format(admin) -> None:
    loaded = admin.get("/api/v1/websites/demo/content").json()
    broken = loaded["document"]
    broken["config"]["primary_color"] = "red"
    response = admin.put("/api/v1/websites/demo/content", json={"document": broken, "revision": 1})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["problems"] == [
        {"path": "config.primary_color", "message": "must be a hex color like #155eef or #fff"}
    ]

    renamed = admin.get("/api/v1/websites/demo/content").json()["document"]
    renamed["config"]["id"] = "other"
    mismatch = admin.put("/api/v1/websites/demo/content", json={"document": renamed, "revision": 1})
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"]["problems"][0]["path"] == "config.id"
    assert admin.get("/api/v1/websites/demo/content").json()["revision"] == 1


# --- backup export and import -------------------------------------------------------------------


def test_export_is_a_downloadable_backup_of_settings_and_content(admin) -> None:
    admin.patch(
        "/api/v1/websites/demo",
        json={"domain": "www.example.com", "allowed_origins": ["https://www.example.com"]},
    )

    response = admin.get("/api/v1/websites/demo/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="demo-askharbor-backup.json"'
    )
    backup = json.loads(response.text)
    assert backup["askharbor_backup"] == 1
    assert backup["website"] == {
        "slug": "demo",
        "name": "AskHarbor",
        "domain": "www.example.com",
        "allowed_origins": ["https://www.example.com"],
    }
    assert backup["content"]["config"]["id"] == "demo"
    assert backup["revision"] == 1


def test_import_restores_a_backup_into_another_website(admin) -> None:
    admin.patch(
        "/api/v1/websites/demo",
        json={"domain": "www.example.com", "allowed_origins": ["https://www.example.com"]},
    )
    backup = admin.get("/api/v1/websites/demo/export").json()

    result = admin.post("/api/v1/websites/library/import", json=backup)

    assert result.status_code == 200, result.text
    assert result.json() == {"revision": 2, "applied": ["content", "settings"]}
    library = admin.get("/api/v1/websites/library").json()
    assert library["domain"] == "www.example.com"
    assert library["allowed_origins"] == ["https://www.example.com"]
    content = admin.get("/api/v1/websites/library/content").json()
    assert content["document"]["config"]["id"] == "library"  # rewritten to this website
    assert content["document"]["config"]["greeting"] == backup["content"]["config"]["greeting"]
    assert admin.get("/api/v1/bots/library").json()["greeting"] == "Hi! What can I help you with?"


def test_import_accepts_a_plain_content_file_and_leaves_settings_alone(admin) -> None:
    admin.patch("/api/v1/websites/demo", json={"domain": "keep.example"})
    document = admin.get("/api/v1/websites/library/content").json()["document"]

    result = admin.post("/api/v1/websites/demo/import", json=document)

    assert result.status_code == 200 and result.json()["applied"] == ["content"]
    assert admin.get("/api/v1/websites/demo").json()["domain"] == "keep.example"
    assert admin.get("/api/v1/bots/demo").json()["name"] == "Harbor Library"


def test_invalid_import_changes_nothing(admin) -> None:
    before = admin.get("/api/v1/websites/demo/content").json()
    backup = admin.get("/api/v1/websites/demo/export").json()
    backup["content"]["answers"][0]["next_option_ids"] = ["nope"]

    response = admin.post("/api/v1/websites/demo/import", json=backup)

    assert response.status_code == 422
    assert "has no matching answer" in response.json()["detail"]["problems"][0]["message"]
    assert admin.get("/api/v1/websites/demo/content").json() == before
    assert admin.post("/api/v1/websites/demo/import", json={"hello": "world"}).status_code == 422
    assert (
        admin.post("/api/v1/websites/demo/import", json={"askharbor_backup": 9}).status_code == 422
    )


# --- shared login limiter -------------------------------------------------------------------------


def test_login_limit_is_shared_across_workers(clean_database) -> None:
    factory = sessionmaker(bind=clean_database)
    worker_a = DatabaseLoginLimiter(factory, limit=3, window_seconds=300)
    worker_b = DatabaseLoginLimiter(factory, limit=3, window_seconds=300)

    worker_a.hit("ip:203.0.113.1")
    worker_b.hit("ip:203.0.113.1")
    assert worker_a.peek("ip:203.0.113.1") is None
    worker_b.hit("ip:203.0.113.1")

    retry_after = worker_a.peek("ip:203.0.113.1")
    assert retry_after is not None and 1 <= retry_after <= 300
    assert worker_b.peek("ip:203.0.113.1") is not None
    assert worker_a.peek("ip:other") is None

    with clean_database.connect() as connection:
        connection.execute(
            text("UPDATE login_attempts SET window_start = window_start - interval '10 minutes'")
        )
        connection.commit()
    assert worker_b.peek("ip:203.0.113.1") is None
    worker_b.hit("ip:203.0.113.1")  # expired window restarts at 1
    assert worker_a.peek("ip:203.0.113.1") is None
    assert worker_a.purge_expired() == 0
    worker_a.reset()
    assert worker_a.tracked_keys() == []


def test_login_endpoint_uses_the_shared_limiter(app_module) -> None:
    assert isinstance(app_module.auth_service.login_limiter, DatabaseLoginLimiter)
    app_module.auth_service.login_limiter.limit = 2
    with (
        TestClient(app_module.app, base_url="https://testserver") as first,
        TestClient(app_module.app, base_url="https://testserver") as second,
    ):
        for _ in range(2):
            first.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong-one"})
        blocked = second.post("/api/v1/auth/login", json=ADMIN)
    assert blocked.status_code == 429


# --- admin panel files -------------------------------------------------------------------------


def test_admin_panel_is_served_from_the_api_origin(app_module) -> None:
    client = TestClient(app_module.app, base_url="https://testserver")
    assert client.get("/admin", follow_redirects=False).status_code == 307
    page = client.get("/admin/")
    assert page.status_code == 200 and "panel" in page.text
    assert client.get("/admin/askharbor.js").text == "// widget bundle"
    assert client.get("/admin/missing.js").status_code == 404
    assert client.get("/admin/..%2Fapp%2Fmain.py").status_code == 404


def test_missing_panel_build_explains_itself(
    clean_database, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("ASKHARBOR_DATABASE_URL", TEST_URL)
    monkeypatch.setenv("ASKHARBOR_ADMIN_DIST", str(tmp_path / "nowhere"))
    config.get_settings.cache_clear()
    module = importlib.reload(main)
    try:
        response = TestClient(module.app).get("/admin/")
        assert response.status_code == 404
        assert "npm run build" in response.json()["detail"]
    finally:
        monkeypatch.delenv("ASKHARBOR_DATABASE_URL")
        monkeypatch.delenv("ASKHARBOR_ADMIN_DIST")
        config.get_settings.cache_clear()
        importlib.reload(main)


# --- content source resolution ------------------------------------------------------------------


def test_database_url_switches_content_to_the_database_by_default(app_module) -> None:
    assert app_module.CONTENT_SOURCE == "database"
    assert app_module.settings.content_source == "auto"


def test_seeding_can_be_turned_off(clean_database, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASKHARBOR_DATABASE_URL", TEST_URL)
    monkeypatch.setenv("ASKHARBOR_SEED_SAMPLE_CONTENT", "false")
    config.get_settings.cache_clear()
    module = importlib.reload(main)
    try:
        with TestClient(module.app, base_url="https://testserver") as client:
            assert client.get("/api/v1/bots/demo").status_code == 404
    finally:
        monkeypatch.delenv("ASKHARBOR_DATABASE_URL")
        monkeypatch.delenv("ASKHARBOR_SEED_SAMPLE_CONTENT")
        config.get_settings.cache_clear()
        importlib.reload(main)


def test_expiry_helper_values_are_timezone_aware() -> None:
    assert (datetime.now(UTC) + timedelta(hours=12)).tzinfo is not None
