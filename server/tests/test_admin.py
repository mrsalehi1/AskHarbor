"""Admin routes: users, websites, memberships, audit; and the access rules every
protected route enforces. Needs PostgreSQL (see conftest)."""

import importlib
from collections.abc import Iterator

import pytest
from conftest import TEST_URL, requires_database
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, main
from app.orm import AuditEntry, LoginSession, User

pytestmark = requires_database

ADMIN = {"username": "admin", "password": "ChangeMeLocal123!"}
ADMIN_NEW = "an-admin-passphrase-2026"
EDITOR_TEMP = "temporary-editor-pw-1"
EDITOR_NEW = "editor-own-passphrase-9"


@pytest.fixture
def app_module(clean_database, monkeypatch: pytest.MonkeyPatch) -> Iterator:
    monkeypatch.setenv("ASKHARBOR_DATABASE_URL", TEST_URL)
    config.get_settings.cache_clear()
    module = importlib.reload(main)
    try:
        yield module
    finally:
        monkeypatch.delenv("ASKHARBOR_DATABASE_URL", raising=False)
        config.get_settings.cache_clear()
        importlib.reload(main)


@pytest.fixture
def admin(app_module) -> Iterator[TestClient]:
    """A signed in admin whose forced password change is done."""
    with TestClient(app_module.app, base_url="https://testserver") as client:
        assert client.post("/api/v1/auth/login", json=ADMIN).status_code == 200
        assert (
            client.post(
                "/api/v1/auth/password",
                json={"current_password": ADMIN["password"], "new_password": ADMIN_NEW},
            ).status_code
            == 200
        )
        yield client


@pytest.fixture
def anonymous(app_module) -> Iterator[TestClient]:
    with TestClient(app_module.app, base_url="https://testserver") as client:
        yield client


def create_editor(admin: TestClient, username: str = "editor", is_admin: bool = False) -> dict:
    response = admin.post(
        "/api/v1/admin/users",
        json={"username": username, "password": EDITOR_TEMP, "is_admin": is_admin},
    )
    assert response.status_code == 201, response.text
    return response.json()


def sign_in(client: TestClient, username: str, password: str) -> int:
    return client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    ).status_code


def finish_password_change(client: TestClient, current: str, new: str) -> None:
    assert (
        client.post(
            "/api/v1/auth/password", json={"current_password": current, "new_password": new}
        ).status_code
        == 200
    )


# --- who may call what ----------------------------------------------------------------


def test_admin_routes_need_a_signed_in_admin(admin, anonymous, app_module) -> None:
    assert anonymous.get("/api/v1/admin/users").status_code == 401
    assert anonymous.get("/api/v1/websites").status_code == 401

    create_editor(admin)
    with TestClient(app_module.app, base_url="https://testserver") as editor:
        assert sign_in(editor, "editor", EDITOR_TEMP) == 200
        # Temporary password: nothing but the change itself is allowed.
        assert editor.get("/api/v1/websites").status_code == 403
        assert editor.get("/api/v1/admin/users").status_code == 403
        finish_password_change(editor, EDITOR_TEMP, EDITOR_NEW)
        # A plain user is still not an admin.
        assert editor.get("/api/v1/websites").status_code == 200
        forbidden = editor.get("/api/v1/admin/users")
        assert forbidden.status_code == 403
        assert forbidden.json()["detail"] == "Admin access required."
        assert (
            editor.post("/api/v1/admin/websites", json={"slug": "x", "name": "X"}).status_code
            == 403
        )


# --- users -----------------------------------------------------------------------------


def test_admin_creates_users_who_must_change_their_temporary_password(admin, app_module) -> None:
    created = create_editor(admin)
    assert created["must_change_password"] is True and created["is_admin"] is False
    assert created["websites"] == []

    listed = {user["username"] for user in admin.get("/api/v1/admin/users").json()}
    assert listed == {"admin", "editor"}

    duplicate = admin.post(
        "/api/v1/admin/users", json={"username": "editor", "password": EDITOR_TEMP}
    )
    assert duplicate.status_code == 409
    bad_name = admin.post(
        "/api/v1/admin/users", json={"username": "not valid", "password": EDITOR_TEMP}
    )
    assert bad_name.status_code == 422
    weak = admin.post("/api/v1/admin/users", json={"username": "weak", "password": "short"})
    assert weak.status_code == 400


def test_deactivated_user_cannot_log_in_and_loses_live_sessions(
    admin, app_module, clean_database
) -> None:
    created = create_editor(admin)
    with TestClient(app_module.app, base_url="https://testserver") as editor:
        assert sign_in(editor, "editor", EDITOR_TEMP) == 200
        assert editor.get("/api/v1/auth/me").status_code == 200

        response = admin.patch(f"/api/v1/admin/users/{created['id']}", json={"is_active": False})
        assert response.status_code == 200 and response.json()["is_active"] is False

        assert editor.get("/api/v1/auth/me").status_code == 401
        assert sign_in(editor, "editor", EDITOR_TEMP) == 401

        admin.patch(f"/api/v1/admin/users/{created['id']}", json={"is_active": True})
        assert sign_in(editor, "editor", EDITOR_TEMP) == 200


def test_password_reset_ends_sessions_and_forces_a_new_password(
    admin, app_module, clean_database
) -> None:
    created = create_editor(admin)
    with TestClient(app_module.app, base_url="https://testserver") as editor:
        sign_in(editor, "editor", EDITOR_TEMP)
        finish_password_change(editor, EDITOR_TEMP, EDITOR_NEW)
        assert editor.get("/api/v1/websites").status_code == 200

        reset = admin.post(
            f"/api/v1/admin/users/{created['id']}/password",
            json={"new_password": "reset-by-the-admin-77"},
        )
        assert reset.status_code == 200 and reset.json()["must_change_password"] is True

        # Old session dead, old password dead, temporary one works but is gated.
        assert editor.get("/api/v1/auth/me").status_code == 401
        assert sign_in(editor, "editor", EDITOR_NEW) == 401
        assert sign_in(editor, "editor", "reset-by-the-admin-77") == 200
        assert editor.get("/api/v1/websites").status_code == 403
    with Session(clean_database) as db:
        live = (
            db.execute(
                select(LoginSession)
                .join(User)
                .where(User.username == "editor", LoginSession.revoked_at.is_(None))
            )
            .scalars()
            .all()
        )
        assert len(live) == 1  # only the newest login


def test_admin_cannot_lock_themselves_out(admin) -> None:
    me = next(u for u in admin.get("/api/v1/admin/users").json() if u["username"] == "admin")
    assert (
        admin.patch(f"/api/v1/admin/users/{me['id']}", json={"is_active": False}).status_code == 400
    )
    assert (
        admin.patch(f"/api/v1/admin/users/{me['id']}", json={"is_admin": False}).status_code == 400
    )
    assert admin.get("/api/v1/auth/me").status_code == 200


def test_admin_can_promote_a_user(admin, app_module) -> None:
    created = create_editor(admin)
    admin.patch(f"/api/v1/admin/users/{created['id']}", json={"is_admin": True})
    with TestClient(app_module.app, base_url="https://testserver") as editor:
        sign_in(editor, "editor", EDITOR_TEMP)
        finish_password_change(editor, EDITOR_TEMP, EDITOR_NEW)
        assert editor.get("/api/v1/admin/users").status_code == 200


# --- websites and memberships ----------------------------------------------------------


def test_sample_websites_are_seeded_once_and_deletions_stick(admin, app_module) -> None:
    slugs = [w["slug"] for w in admin.get("/api/v1/admin/websites").json()]
    assert slugs == ["demo", "library"]
    assert admin.get("/api/v1/bots/library").status_code == 200

    assert admin.delete("/api/v1/admin/websites/library").status_code == 204
    assert admin.get("/api/v1/bots/library").status_code == 404

    # A restart runs the startup logic again: no re-seeding into a non-empty table.
    with TestClient(app_module.app, base_url="https://testserver"):
        pass
    assert [w["slug"] for w in admin.get("/api/v1/admin/websites").json()] == ["demo"]


def test_new_website_gets_a_starter_bot_and_serves_the_widget(admin) -> None:
    response = admin.post(
        "/api/v1/admin/websites",
        json={"slug": "shop", "name": "Harbor Shop", "domain": "Shop.Example.com"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["domain"] == "shop.example.com" and body["members"] == []

    public = admin.get("/api/v1/bots/shop")
    assert public.status_code == 200
    assert public.json()["name"] == "Harbor Shop"
    assert [o["id"] for o in public.json()["options"]] == ["example-question"]

    assert (
        admin.post("/api/v1/admin/websites", json={"slug": "shop", "name": "Again"}).status_code
        == 409
    )
    assert (
        admin.post("/api/v1/admin/websites", json={"slug": "bad slug", "name": "X"}).status_code
        == 422
    )
    assert (
        admin.post(
            "/api/v1/admin/websites", json={"slug": "ok", "name": "X", "domain": "not a domain"}
        ).status_code
        == 422
    )


def test_members_see_and_edit_only_their_websites(admin, app_module) -> None:
    created = create_editor(admin)
    admin.post("/api/v1/admin/websites", json={"slug": "shop", "name": "Shop"})
    added = admin.post("/api/v1/admin/websites/shop/members", json={"user_id": created["id"]})
    assert added.status_code == 201 and added.json()["members"] == ["editor"]

    with TestClient(app_module.app, base_url="https://testserver") as editor:
        sign_in(editor, "editor", EDITOR_TEMP)
        finish_password_change(editor, EDITOR_TEMP, EDITOR_NEW)

        assert [w["slug"] for w in editor.get("/api/v1/websites").json()] == ["shop"]
        assert editor.get("/api/v1/websites/shop").status_code == 200
        assert editor.get("/api/v1/websites/shop/content").status_code == 200
        # Other websites look like they do not exist, on every route.
        for path in (
            "/api/v1/websites/demo",
            "/api/v1/websites/demo/content",
            "/api/v1/websites/demo/export",
            "/api/v1/websites/demo/audit",
        ):
            assert editor.get(path).status_code == 404, path
        assert editor.patch("/api/v1/websites/demo", json={"name": "Hijack"}).status_code == 404
        demo_content = admin.get("/api/v1/websites/demo/content").json()
        assert editor.put("/api/v1/websites/demo/content", json=demo_content).status_code == 404

        removed = admin.delete(f"/api/v1/admin/websites/shop/members/{created['id']}")
        assert removed.status_code == 200 and removed.json()["members"] == []
        assert editor.get("/api/v1/websites").json() == []
        assert editor.get("/api/v1/websites/shop").status_code == 404

    assert admin.get("/api/v1/websites/demo").json()["name"] == "AskHarbor"


def test_member_routes_report_missing_websites_and_users(admin) -> None:
    assert admin.post("/api/v1/admin/websites/nope/members", json={"user_id": 1}).status_code == 404
    assert (
        admin.post("/api/v1/admin/websites/demo/members", json={"user_id": 999}).status_code == 404
    )
    assert admin.delete("/api/v1/admin/websites/nope").status_code == 404


# --- audit ---------------------------------------------------------------------------------


def test_admin_actions_are_audited(admin, clean_database) -> None:
    created = create_editor(admin)
    admin.post("/api/v1/admin/websites", json={"slug": "shop", "name": "Shop"})
    admin.post("/api/v1/admin/websites/shop/members", json={"user_id": created["id"]})
    admin.post(
        f"/api/v1/admin/users/{created['id']}/password", json={"new_password": "reset-by-admin-123"}
    )

    log = admin.get("/api/v1/admin/audit").json()
    actions = [entry["action"] for entry in log]
    for expected in (
        "login",
        "password_change",
        "user_create",
        "website_create",
        "member_add",
        "user_password_reset",
    ):
        assert expected in actions, actions
    reset_entry = next(e for e in log if e["action"] == "user_password_reset")
    assert reset_entry["username"] == "admin"
    assert reset_entry["details"] == {"username": "editor"}
    assert reset_entry["client_address"] is not None
    member_entry = next(e for e in log if e["action"] == "member_add")
    assert member_entry["website_slug"] == "shop"

    with Session(clean_database) as db:
        assert db.execute(select(AuditEntry)).scalars().all().__len__() == len(log)


def test_failed_logins_are_audited_without_a_user(anonymous) -> None:
    anonymous.post("/api/v1/auth/login", json={"username": "ghost", "password": "wrong-pw-123"})
    with TestClient(anonymous.app, base_url="https://testserver") as admin:
        admin.post("/api/v1/auth/login", json=ADMIN)
        admin.post(
            "/api/v1/auth/password",
            json={"current_password": ADMIN["password"], "new_password": ADMIN_NEW},
        )
        failed = [
            e for e in admin.get("/api/v1/admin/audit").json() if e["action"] == "login_failed"
        ]
    assert failed and failed[0]["username"] is None and failed[0]["target_id"] == "ghost"
