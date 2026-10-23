import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import AnswerNode, BotConfig, BotDefinition, ChatOption
from app.repository import repository

client = TestClient(app)


def build_bot(bot_id: str, answers: dict[str, AnswerNode], opening: list[str]) -> BotDefinition:
    config = BotConfig(
        id=bot_id,
        name="Broken",
        greeting="Hi",
        launcher_label="Open",
        primary_color="#000000",
        options=[ChatOption(id=option_id, label=option_id) for option_id in opening],
    )
    return BotDefinition(config=config, answers=answers)


def test_follow_up_pointing_at_missing_answer_is_rejected_with_details() -> None:
    answers = {
        "start": AnswerNode(label="Start", answer="Hello", next_option_ids=["pricng"]),
        "pricing": AnswerNode(label="Pricing", answer="Free"),
    }
    with pytest.raises(ValidationError) as excinfo:
        build_bot("shop-bot", answers, ["start"])

    message = str(excinfo.value)
    assert "shop-bot" in message
    assert "'start'" in message
    assert "'pricng'" in message


def test_opening_option_pointing_at_missing_answer_is_rejected() -> None:
    answers = {"start": AnswerNode(label="Start", answer="Hello")}
    with pytest.raises(ValidationError) as excinfo:
        build_bot("shop-bot", answers, ["start", "missing-opening"])

    message = str(excinfo.value)
    assert "shop-bot" in message
    assert "'missing-opening'" in message


def test_valid_bot_is_accepted() -> None:
    answers = {
        "start": AnswerNode(label="Start", answer="Hello", next_option_ids=["pricing"]),
        "pricing": AnswerNode(label="Pricing", answer="Free"),
    }
    bot = build_bot("ok-bot", answers, ["start"])
    assert [option.id for option in bot.config.options] == ["start"]


def test_demo_bot_references_are_all_valid() -> None:
    bot = repository.get("demo")
    assert bot is not None
    referenced = {oid for node in bot.answers.values() for oid in node.next_option_ids}
    referenced |= {option.id for option in bot.config.options}
    assert referenced <= set(bot.answers)


def test_message_endpoint_reports_missing_reference_instead_of_dropping_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Bypass model validation to simulate content that slipped through, for example
    # from a future file loader. The endpoint must not silently hide the problem.
    broken = BotDefinition.model_construct(
        config=BotConfig(
            id="broken",
            name="Broken",
            greeting="Hi",
            launcher_label="Open",
            primary_color="#000000",
            options=[ChatOption(id="start", label="Start")],
        ),
        answers={
            "start": AnswerNode(label="Start", answer="Hello", next_option_ids=["pricng"]),
        },
    )
    monkeypatch.setitem(repository._bots, "broken", broken)

    response = client.post("/api/v1/bots/broken/messages", json={"option_id": "start"})

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "broken" in detail
    assert "start" in detail
    assert "pricng" in detail
