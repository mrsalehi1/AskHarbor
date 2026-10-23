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
