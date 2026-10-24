import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings

ENV_VAR = "ASKHARBOR_ALLOWED_ORIGINS"


def make_settings(monkeypatch: pytest.MonkeyPatch, value: str | None) -> Settings:
    if value is None:
        monkeypatch.delenv(ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(ENV_VAR, value)
    return Settings(_env_file=None)


def test_unset_variable_keeps_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(monkeypatch, None)
    assert settings.allowed_origins == "*"
    assert settings.cors_origins == ["*"]


def test_explicit_wildcard_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    assert make_settings(monkeypatch, "*").cors_origins == ["*"]


def test_origin_list_is_split_and_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(monkeypatch, "https://www.example.com, https://app.example.com")
    assert settings.cors_origins == ["https://www.example.com", "https://app.example.com"]


@pytest.mark.parametrize("value", ["", "   ", " , ,", ",,,"])
def test_blank_value_refuses_to_start(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        make_settings(monkeypatch, value)
    message = str(excinfo.value)
    assert ENV_VAR in message
    assert "remove the variable" in message
    assert "https://www.example.com" in message


def test_get_settings_fails_fast_on_blank_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValidationError, match=ENV_VAR):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_trailing_slash_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(monkeypatch, "https://example.com/")
    assert settings.cors_origins == ["https://example.com"]


def test_repeated_trailing_slashes_are_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(monkeypatch, "https://example.com///")
    assert settings.cors_origins == ["https://example.com"]


def test_spaces_and_trailing_slash_together(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(monkeypatch, "  https://example.com/  ")
    assert settings.cors_origins == ["https://example.com"]


def test_multiple_origins_with_trailing_slashes(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(monkeypatch, "https://www.example.com/, https://app.example.com/")
    assert settings.cors_origins == ["https://www.example.com", "https://app.example.com"]


def test_origins_with_ports_keep_the_port(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(monkeypatch, "http://localhost:3000/, https://example.com:8443/")
    assert settings.cors_origins == ["http://localhost:3000", "https://example.com:8443"]


def test_slash_only_value_refuses_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match=ENV_VAR):
        make_settings(monkeypatch, "/, //")


# --- content directory -------------------------------------------------------

CONTENT_VAR = "ASKHARBOR_CONTENT_DIR"


def test_content_dir_defaults_to_the_server_content_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(CONTENT_VAR, raising=False)
    settings = Settings(_env_file=None)
    assert settings.content_dir.name == "content"
    assert settings.content_dir.parent.name == "server"
    assert (settings.content_dir / "demo.json").is_file()


def test_content_dir_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONTENT_VAR, "/srv/askharbor/bots")
    settings = Settings(_env_file=None)
    assert str(settings.content_dir) == "/srv/askharbor/bots"


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_content_dir_refuses_to_start(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(CONTENT_VAR, value)
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    message = str(excinfo.value)
    assert CONTENT_VAR in message
    assert "server/content" in message


# --- accounts ------------------------------------------------------------------

DB_URL = "postgresql+psycopg://askharbor:secret@127.0.0.1:5432/askharbor"


def production(monkeypatch: pytest.MonkeyPatch, **values: str) -> Settings:
    monkeypatch.setenv("ASKHARBOR_ENV", "production")
    monkeypatch.setenv("ASKHARBOR_DATABASE_URL", DB_URL)
    for name in (
        "ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD",
        "ASKHARBOR_BOOTSTRAP_ADMIN_USERNAME",
        "ASKHARBOR_COOKIE_SECURE",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_development_accepts_the_documented_local_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASKHARBOR_ENV", raising=False)
    monkeypatch.delenv("ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("ASKHARBOR_DATABASE_URL", DB_URL)
    settings = Settings(_env_file=None)
    assert settings.env == "development"
    assert settings.bootstrap_admin_username == "admin"
    assert settings.bootstrap_admin_password is None
    assert settings.effective_bootstrap_password == "ChangeMeLocal123!"
    assert settings.session_hours == 12
    assert settings.cookie_secure is True
    assert settings.accounts_enabled is True


def test_production_without_a_bootstrap_password_starts_but_cannot_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Removing the variable after the first start must not stop the server."""
    settings = production(monkeypatch)
    assert settings.bootstrap_admin_password is None
    assert settings.effective_bootstrap_password is None


def test_production_refuses_the_default_admin_password(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError) as excinfo:
        production(monkeypatch, ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD="ChangeMeLocal123!")
    message = str(excinfo.value)
    assert "ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD" in message
    assert "local development password" in message
    assert "ChangeMeLocal123!" not in message


def test_production_refuses_a_short_admin_password(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="shorter than 12"):
        production(monkeypatch, ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD="short")


def test_production_accepts_its_own_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = production(
        monkeypatch,
        ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD="a-real-secret-chosen-by-ops",
        ASKHARBOR_BOOTSTRAP_ADMIN_USERNAME="ops-admin",
    )
    assert settings.bootstrap_admin_username == "ops-admin"


def test_production_refuses_insecure_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="ASKHARBOR_COOKIE_SECURE"):
        production(
            monkeypatch,
            ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD="a-real-secret-chosen-by-ops",
            ASKHARBOR_COOKIE_SECURE="false",
        )


def test_production_without_accounts_does_not_need_a_bootstrap_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASKHARBOR_ENV", "production")
    monkeypatch.delenv("ASKHARBOR_DATABASE_URL", raising=False)
    monkeypatch.delenv("ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    settings = Settings(_env_file=None)
    assert settings.accounts_enabled is False


def test_accounts_are_disabled_without_a_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASKHARBOR_DATABASE_URL", raising=False)
    assert Settings(_env_file=None).accounts_enabled is False
