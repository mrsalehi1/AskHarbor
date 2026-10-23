"""Login, sessions, forced password change, CSRF, rate limits and bootstrap.

These need PostgreSQL (see conftest). The app runs in file mode with a
database configured for accounts, which is the local development setup the
README documents. The test client uses an https base URL so the Secure cookie
is actually sent back, as a browser would.
"""

import importlib
import logging
import threading
from collections.abc import Iterator
from datetime import timedelta

import pytest
from conftest import TEST_URL, requires_database
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import auth, config, main
from app.auth_routes import COOKIE_NAME, PASSWORD_CHANGE_REQUIRED
from app.orm import LoginSession, User, Website, WebsiteMember

pytestmark = requires_database

ADMIN = {"username": "admin", "password": "ChangeMeLocal123!"}
NEW_PASSWORD = "a-much-better-passphrase-42"


@pytest.fixture
def app_module(clean_database, monkeypatch: pytest.MonkeyPatch) -> Iterator:
    """The app in file mode with accounts enabled against the test database."""
    monkeypatch.setenv("ASKHARBOR_DATABASE_URL", TEST_URL)
    monkeypatch.setenv("ASKHARBOR_CONTENT_SOURCE", "files")
    config.get_settings.cache_clear()
    module = importlib.reload(main)
    try:
        yield module
    finally:
        monkeypatch.delenv("ASKHARBOR_DATABASE_URL", raising=False)
        monkeypatch.delenv("ASKHARBOR_CONTENT_SOURCE", raising=False)
        config.get_settings.cache_clear()
        importlib.reload(main)


@pytest.fixture
def client(app_module) -> Iterator[TestClient]:
    """Runs the lifespan, so the bootstrap admin exists."""
    with TestClient(app_module.app, base_url="https://testserver") as client:
        yield client


def login(client: TestClient, **overrides: str):
    return client.post("/api/v1/auth/login", json={**ADMIN, **overrides})


def change_password(client: TestClient, current: str = ADMIN["password"], new: str = NEW_PASSWORD):
    return client.post(
        "/api/v1/auth/password", json={"current_password": current, "new_password": new}
    )


# --- bootstrap --------------------------------------------------------------------


def test_bootstrap_creates_one_admin_that_must_change_its_password(client, clean_database) -> None:
    with Session(clean_database) as db:
        users = db.execute(select(User)).scalars().all()
    assert [(u.username, u.is_admin, u.must_change_password) for u in users] == [
        ("admin", True, True)
    ]
    assert users[0].password_hash.startswith("$argon2id$")
    assert ADMIN["password"] not in users[0].password_hash


def test_bootstrap_runs_only_once(app_module, clean_database, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="askharbor"):
        app_module.prepare_accounts()
        app_module.prepare_accounts()
    with Session(clean_database) as db:
        assert db.execute(select(User)).scalars().all().__len__() == 1
    assert "Bootstrap admin 'admin' created" in caplog.text
    assert "Bootstrap admin skipped: 1 account(s) already exist" in caplog.text


def test_bootstrap_is_safe_when_several_workers_start_together(clean_database) -> None:
    settings = config.Settings(_env_file=None, database_url=TEST_URL)
    created: list[bool] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(6)

    def worker() -> None:
        try:
            barrier.wait()
            with Session(clean_database) as db, db.begin():
                created.append(auth.bootstrap_admin(db, settings))
        except Exception as error:  # pragma: no cover - reported by the assertion below
            errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert created.count(True) == 1 and created.count(False) == 5
    with Session(clean_database) as db:
        assert db.execute(select(User)).scalars().all().__len__() == 1


def test_restart_does_not_restore_the_old_password(app_module, clean_database) -> None:
    with TestClient(app_module.app, base_url="https://testserver") as client:
        assert login(client).status_code == 200
        assert change_password(client).status_code == 200

    # A restart runs the lifespan and therefore the bootstrap again.
    with TestClient(app_module.app, base_url="https://testserver") as restarted:
        assert login(restarted).status_code == 401
        assert login(restarted, password=NEW_PASSWORD).status_code == 200
        assert restarted.get("/api/v1/auth/me").json()["must_change_password"] is False
    with Session(clean_database) as db:
        assert db.execute(select(User)).scalars().all().__len__() == 1


# --- login, logout and sessions ----------------------------------------------------


def test_login_sets_a_secure_http_only_cookie_and_a_12_hour_session(client, clean_database) -> None:
    response = login(client)

    assert response.status_code == 200
    assert response.json() == {"username": "admin", "is_admin": True, "must_change_password": True}
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "Path=/" in cookie and f"Max-Age={12 * 3600}" in cookie
    token = client.cookies.get(COOKIE_NAME)
    assert token and len(token) >= 40

    with Session(clean_database) as db:
        stored = db.execute(select(LoginSession)).scalar_one()
    assert stored.token_hash == auth.hash_token(token)
    assert token not in stored.token_hash
    assert stored.expires_at - stored.created_at == timedelta(hours=12)
    assert stored.revoked_at is None


def test_wrong_password_and_unknown_user_get_the_same_answer(client) -> None:
    wrong = login(client, password="not-the-password")
    unknown = login(client, username="nobody", password="whatever-here")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid username or password."}
    assert "set-cookie" not in wrong.headers
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_requires_a_live_session(client) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401
    login(client)
    assert client.get("/api/v1/auth/me").status_code == 200
    client.cookies.set(COOKIE_NAME, "forged-token-value")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_revokes_the_session_and_clears_the_cookie(client, clean_database) -> None:
    login(client)
    token = client.cookies.get(COOKIE_NAME)

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"] or "expires=" in response.headers[
        "set-cookie"
    ].lower()
    assert client.get("/api/v1/auth/me").status_code == 401
    # Replaying the old cookie does not work either: the row is revoked, not just forgotten.
    client.cookies.set(COOKIE_NAME, token)
    assert client.get("/api/v1/auth/me").status_code == 401
    with Session(clean_database) as db:
        stored = db.execute(select(LoginSession)).scalar_one()
    assert stored.revoked_at is not None


def test_logout_without_a_session_is_harmless(client) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_expired_sessions_are_rejected(client, clean_database) -> None:
    login(client)
    assert client.get("/api/v1/auth/me").status_code == 200

    with clean_database.connect() as connection:
        connection.execute(text("UPDATE sessions SET expires_at = now() - interval '1 minute'"))
        connection.commit()

    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client).status_code == 200  # a fresh login works again


def test_startup_purges_long_expired_sessions(app_module, clean_database) -> None:
    with TestClient(app_module.app, base_url="https://testserver") as client:
        login(client)
    with clean_database.connect() as connection:
        connection.execute(text("UPDATE sessions SET expires_at = now() - interval '2 days'"))
        connection.commit()

    with TestClient(app_module.app, base_url="https://testserver"):
        pass

    with Session(clean_database) as db:
        assert db.execute(select(LoginSession)).first() is None


def test_deactivated_users_cannot_log_in_or_keep_sessions(client, clean_database) -> None:
    login(client)
    with clean_database.connect() as connection:
        connection.execute(text("UPDATE users SET is_active = false"))
        connection.commit()

    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client).status_code == 401


# --- forced password change --------------------------------------------------------


def test_nothing_else_works_until_the_password_is_changed(client) -> None:
    login(client)
    assert client.get("/api/v1/auth/me").json()["must_change_password"] is True

    blocked = client.get("/api/v1/websites")

    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == PASSWORD_CHANGE_REQUIRED

    assert change_password(client).status_code == 200
    assert client.get("/api/v1/auth/me").json()["must_change_password"] is False
    assert client.get("/api/v1/websites").status_code == 200


def test_password_change_checks_the_current_password_and_the_policy(client) -> None:
    login(client)
    assert change_password(client, current="wrong-current-pw").status_code == 400
    assert "not correct" in change_password(client, current="wrong-current-pw").json()["detail"]
    assert "at least 12" in change_password(client, new="short").json()["detail"]
    assert "must differ" in change_password(client, new=ADMIN["password"]).json()["detail"]
    assert client.get("/api/v1/auth/me").json()["must_change_password"] is True


def test_password_change_signs_out_other_sessions(app_module) -> None:
    with (
        TestClient(app_module.app, base_url="https://testserver") as first,
        TestClient(app_module.app, base_url="https://testserver") as second,
    ):
        login(first)
        login(second)
        assert second.get("/api/v1/auth/me").status_code == 200

        assert change_password(first).status_code == 200

        assert first.get("/api/v1/auth/me").status_code == 200
        assert second.get("/api/v1/auth/me").status_code == 401
        assert login(second, password=NEW_PASSWORD).status_code == 200


def test_password_change_requires_a_session(client) -> None:
    assert change_password(client).status_code == 401


# --- cross-site protection -----------------------------------------------------------


def test_login_from_another_origin_is_rejected(client) -> None:
    response = client.post(
        "/api/v1/auth/login", json=ADMIN, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Cross-site request rejected."

    same = client.post("/api/v1/auth/login", json=ADMIN, headers={"Origin": "https://testserver"})
    assert same.status_code == 200


def test_referer_from_another_site_is_rejected(client) -> None:
    login(client)
    response = client.post(
        "/api/v1/auth/password",
        json={"current_password": ADMIN["password"], "new_password": NEW_PASSWORD},
        headers={"Referer": "https://evil.example/page"},
    )
    assert response.status_code == 403


def test_form_encoded_login_is_not_accepted(client) -> None:
    response = client.post("/api/v1/auth/login", data=ADMIN)
    assert response.status_code == 422


def test_account_routes_do_not_get_cors_headers(client) -> None:
    public = client.get("/api/v1/bots/demo", headers={"Origin": "https://shop.example"})
    assert public.headers.get("access-control-allow-origin") == "*"

    account = client.post(
        "/api/v1/auth/logout", headers={"Origin": "https://shop.example"}
    )
    assert "access-control-allow-origin" not in account.headers
    preflight = client.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://shop.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in preflight.headers


# --- login rate limit ------------------------------------------------------------------


def test_failed_logins_are_limited_and_successes_do_not_count(app_module, clean_database) -> None:
    app_module.auth_service.login_limiter.limit = 3
    with TestClient(app_module.app, base_url="https://testserver") as client:
        for _ in range(3):
            assert login(client).status_code == 200  # successes never consume budget
        for _ in range(3):
            assert login(client, password="wrong-password-1").status_code == 401

        blocked = login(client)  # even the right password is refused now

        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) >= 1
        assert "Too many login attempts" in blocked.json()["detail"]


def test_login_limit_also_applies_per_username(app_module) -> None:
    app_module.auth_service.login_limiter.limit = 2
    with (
        TestClient(app_module.app, base_url="https://testserver") as attacker,
        TestClient(app_module.app, base_url="https://testserver") as victim,
    ):
        for _ in range(2):
            attacker.post("/api/v1/auth/login", json={"username": "admin", "password": "guess"})
        # Same username from a different "address" is still blocked...
        blocked = victim.post(
            "/api/v1/auth/login",
            json=ADMIN,
            headers={"X-Forwarded-For": "203.0.113.9"},  # not read; same client anyway
        )
        assert blocked.status_code == 429


# --- websites listing is scoped ---------------------------------------------------------


def test_website_list_shows_all_to_admins_and_only_memberships_to_others(
    client, clean_database
) -> None:
    login(client)
    change_password(client)
    with Session(clean_database) as db, db.begin():
        shop = Website(slug="shop", name="Shop")
        blog = Website(slug="blog", name="Blog")
        editor = User(
            username="editor",
            password_hash=auth.hash_password("editor-passphrase-1"),
            must_change_password=False,
        )
        db.add_all([shop, blog, editor])
        db.flush()
        db.add(WebsiteMember(website_id=shop.id, user_id=editor.id))

    # The sample bots are seeded into the empty database at startup; admins see everything.
    assert [w["slug"] for w in client.get("/api/v1/websites").json()] == [
        "blog",
        "demo",
        "library",
        "shop",
    ]

    client.post("/api/v1/auth/logout")
    assert login(client, username="editor", password="editor-passphrase-1").status_code == 200
    assert [w["slug"] for w in client.get("/api/v1/websites").json()] == ["shop"]


# --- without a database ---------------------------------------------------------------


def test_account_routes_explain_when_accounts_are_not_configured() -> None:
    plain = TestClient(main.app)  # the default app: file mode, no database URL
    response = plain.post("/api/v1/auth/login", json=ADMIN)
    assert response.status_code == 503
    assert "ASKHARBOR_DATABASE_URL" in response.json()["detail"]
    assert plain.get("/api/v1/auth/me").status_code == 503
    assert plain.get("/api/v1/bots/demo").status_code == 200
