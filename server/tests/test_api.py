from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_returns_bot_configuration() -> None:
    response = client.get("/api/v1/bots/demo")
    body = response.json()

    assert response.status_code == 200
    assert body["name"] == "AskHarbor"
    assert len(body["options"]) == 3


def test_returns_answer_and_follow_up_options() -> None:
    response = client.post(
        "/api/v1/bots/demo/messages",
        json={"option_id": "getting-started"},
    )
    body = response.json()

    assert response.status_code == 200
    assert "script" in body["answer"]
    assert [option["id"] for option in body["options"]] == ["installation", "customize"]


def test_rejects_unknown_bot_and_option() -> None:
    assert client.get("/api/v1/bots/missing").status_code == 404
    response = client.post(
        "/api/v1/bots/demo/messages",
        json={"option_id": "missing"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown option"


def test_validates_empty_option() -> None:
    response = client.post("/api/v1/bots/demo/messages", json={"option_id": ""})
    assert response.status_code == 422
