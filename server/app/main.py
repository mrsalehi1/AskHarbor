from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .models import BotConfig, ChatOption, MessageRequest, MessageResponse
from .repository import repository

app = FastAPI(title="AskHarbor API", version="0.1.5")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_origins != ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/bots/{bot_id}", response_model=BotConfig)
def get_bot(bot_id: str) -> BotConfig:
    bot = repository.get(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot.config


@app.post("/api/v1/bots/{bot_id}/messages", response_model=MessageResponse)
def create_message(bot_id: str, message: MessageRequest) -> MessageResponse:
    bot = repository.get(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")

    node = bot.answers.get(message.option_id)
    if node is None:
        raise HTTPException(status_code=400, detail="Unknown option")

    options = [
        ChatOption(id=option_id, label=bot.answers[option_id].label)
        for option_id in node.next_option_ids
        if option_id in bot.answers
    ]
    return MessageResponse(answer=node.answer, options=options)
