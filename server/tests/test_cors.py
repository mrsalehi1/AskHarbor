import importlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture
def client_with_trailing_slash_origin(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """App configured with a trailing slash origin, as a site owner might paste it."""
    monkeypatch.setenv("ASKHARBOR_ALLOWED_ORIGINS", "https://example.com/")
    get_settings.cache_clear()
    import app.main

    module = importlib.reload(app.main)
    try:
        yield TestClient(module.app)
    finally:
        get_settings.cache_clear()


def test_matching_browser_origin_is_allowed(
    client_with_trailing_slash_origin: TestClient,
) -> None:
    response = client_with_trailing_slash_origin.get(
        "/health", headers={"Origin": "https://example.com"}
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://example.com"


def test_unrelated_origin_is_still_blocked(
    client_with_trailing_slash_origin: TestClient,
) -> None:
    response = client_with_trailing_slash_origin.get(
        "/health", headers={"Origin": "https://evil.example"}
    )
    assert "access-control-allow-origin" not in response.headers

    preflight = client_with_trailing_slash_origin.options(
        "/api/v1/bots/demo/messages",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 400
