import pytest

from app import main


@pytest.fixture(autouse=True)
def reset_message_limiter():
    """Keep the in-memory request counter from leaking between tests."""
    main.message_limiter.reset()
    yield
    main.message_limiter.reset()
