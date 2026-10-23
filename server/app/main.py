import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .models import BotConfig, ChatOption, MessageRequest, MessageResponse
from .rate_limit import FixedWindowRateLimiter
from .repository import repository
from .version import get_version

logger = logging.getLogger("askharbor")

app = FastAPI(title="AskHarbor API", version=get_version())

settings = get_settings()
message_limiter = FixedWindowRateLimiter(
    limit=settings.message_rate_limit,
    window_seconds=settings.message_rate_window_seconds,
)
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
def create_message(bot_id: str, message: MessageRequest, request: Request) -> MessageResponse:
    client_key = request.client.host if request.client else "unknown"
    retry_after = message_limiter.hit(client_key)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    bot = repository.get(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")

    node = bot.answers.get(message.option_id)
    if node is None:
        raise HTTPException(status_code=400, detail="Unknown option")

    missing = [oid for oid in node.next_option_ids if oid not in bot.answers]
    if missing:
        detail = (
            f"Bot '{bot_id}' answer '{message.option_id}' references missing option(s) "
            f"{', '.join(repr(oid) for oid in missing)}"
        )
        logger.error(detail)
        raise HTTPException(status_code=500, detail=detail)

    options = [
        ChatOption(id=option_id, label=bot.answers[option_id].label)
        for option_id in node.next_option_ids
    ]
    return MessageResponse(answer=node.answer, options=options)
