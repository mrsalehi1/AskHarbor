import importlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.config import Settings
from app.rate_limit import FixedWindowRateLimiter

ENV_LIMIT = "ASKHARBOR_MESSAGE_RATE_LIMIT"
ENV_WINDOW = "ASKHARBOR_MESSAGE_RATE_WINDOW_SECONDS"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# --- limiter unit tests -----------------------------------------------------


def test_requests_within_the_limit_are_allowed() -> None:
    limiter = FixedWindowRateLimiter(limit=3, window_seconds=60, clock=FakeClock())
    assert [limiter.hit("a") for _ in range(3)] == [None, None, None]


def test_request_over_the_limit_returns_seconds_until_the_window_resets() -> None:
    clock = FakeClock()
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=60, clock=clock)
    limiter.hit("a")
    clock.now += 10
    limiter.hit("a")

    retry_after = limiter.hit("a")

    assert retry_after == 50


def test_retry_after_is_at_least_one_second() -> None:
    clock = FakeClock()
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("a")
    clock.now += 59.9
    assert limiter.hit("a") == 1


def test_budget_recovers_after_the_window() -> None:
    clock = FakeClock()
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("a")
    assert limiter.hit("a") is not None
    clock.now += 60
    assert limiter.hit("a") is None


def test_clients_are_tracked_separately() -> None:
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60, clock=FakeClock())
    assert limiter.hit("a") is None
    assert limiter.hit("b") is None
    assert limiter.hit("a") is not None


def test_tracking_is_bounded_and_evicts_expired_clients_first() -> None:
    clock = FakeClock()
    limiter = FixedWindowRateLimiter(limit=5, window_seconds=60, max_clients=3, clock=clock)
    limiter.hit("old")
    clock.now += 61
    limiter.hit("b")
    limiter.hit("c")
    limiter.hit("d")

    assert limiter.tracked_clients == 3
    assert "old" not in limiter.tracked_keys()


def test_tracking_evicts_the_oldest_live_client_when_full() -> None:
    clock = FakeClock()
    limiter = FixedWindowRateLimiter(limit=5, window_seconds=60, max_clients=2, clock=clock)
    limiter.hit("a")
    clock.now += 1
    limiter.hit("b")
    clock.now += 1
    limiter.hit("c")

    assert limiter.tracked_clients == 2
    assert limiter.tracked_keys() == ["b", "c"]


def test_limit_of_zero_disables_the_limiter() -> None:
    limiter = FixedWindowRateLimiter(limit=0, window_seconds=60, clock=FakeClock())
    assert all(limiter.hit("a") is None for _ in range(100))
    assert limiter.tracked_clients == 0


# --- settings ---------------------------------------------------------------


def test_default_limit_is_thirty_requests_per_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_LIMIT, raising=False)
    monkeypatch.delenv(ENV_WINDOW, raising=False)
    settings = Settings(_env_file=None)
    assert settings.message_rate_limit == 30
    assert settings.message_rate_window_seconds == 60


def test_limit_and_window_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_LIMIT, "5")
    monkeypatch.setenv(ENV_WINDOW, "10")
    settings = Settings(_env_file=None)
    assert settings.message_rate_limit == 5
    assert settings.message_rate_window_seconds == 10


@pytest.mark.parametrize(
    ("name", "value"), [(ENV_LIMIT, "-1"), (ENV_WINDOW, "0"), (ENV_LIMIT, "x")]
)
def test_invalid_limit_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        Settings(_env_file=None)


# --- endpoint behaviour -----------------------------------------------------


@pytest.fixture
def limited_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, FakeClock]]:
    monkeypatch.setenv(ENV_LIMIT, "3")
    monkeypatch.setenv(ENV_WINDOW, "60")
    config.get_settings.cache_clear()
    module = importlib.reload(main)
    clock = FakeClock()
    module.message_limiter.clock = clock
    try:
        yield TestClient(module.app), clock
    finally:
        monkeypatch.delenv(ENV_LIMIT, raising=False)
        monkeypatch.delenv(ENV_WINDOW, raising=False)
        config.get_settings.cache_clear()
        importlib.reload(main)


def ask(client: TestClient, option_id: str = "contact"):
    return client.post("/api/v1/bots/demo/messages", json={"option_id": option_id})


def test_messages_over_the_limit_get_429_with_retry_after(limited_app) -> None:
    client, _ = limited_app
    assert [ask(client).status_code for _ in range(3)] == [200, 200, 200]

    response = ask(client)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert "60 seconds" in response.json()["detail"]


def test_health_and_bot_config_are_not_limited(limited_app) -> None:
    client, _ = limited_app
    for _ in range(4):
        ask(client)
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/bots/demo").status_code == 200


def test_limited_conversation_recovers_after_the_window(limited_app) -> None:
    client, clock = limited_app
    for _ in range(3):
        ask(client)
    assert ask(client).status_code == 429

    clock.now += 60

    response = ask(client, "getting-started")
    assert response.status_code == 200
    assert [option["id"] for option in response.json()["options"]] == ["installation", "customize"]


def test_rejected_requests_do_not_consume_budget_after_reset(limited_app) -> None:
    client, clock = limited_app
    for _ in range(6):
        ask(client)
    clock.now += 60
    assert [ask(client).status_code for _ in range(3)] == [200, 200, 200]
    assert ask(client).status_code == 429
