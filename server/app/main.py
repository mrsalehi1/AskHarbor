import asyncio
import logging
import signal
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .content import ContentLoadError, load_content_directory
from .models import BotConfig, ChatOption, MessageRequest, MessageResponse
from .rate_limit import FixedWindowRateLimiter
from .repository import BotRepository
from .version import get_version

logger = logging.getLogger("askharbor")

settings = get_settings()


def _load_startup_content() -> BotRepository:
    """Load every bot once at startup, or stop with the full list of problems."""
    try:
        return BotRepository(load_content_directory(settings.content_dir))
    except ContentLoadError as error:
        raise SystemExit(
            f"AskHarbor cannot start because the bot content in {settings.content_dir} "
            f"is invalid. Fix the files below or point ASKHARBOR_CONTENT_DIR at a valid "
            f"directory.\n{error}"
        ) from None


repository = _load_startup_content()


def reload_content() -> bool:
    """Reload every bot from the content directory and swap the set atomically.

    The new set replaces the old one only when every file validates. Otherwise
    the problems are logged and the bots already loaded keep being served.
    Returns True when the swap happened.
    """
    try:
        bots = load_content_directory(settings.content_dir)
    except ContentLoadError as error:
        logger.error(
            "Content reload rejected, keeping the %d bot(s) already loaded (%s).\n%s",
            len(repository.ids()),
            ", ".join(repository.ids()),
            error,
        )
        return False
    repository.replace(bots)
    logger.info("Content reloaded from %s: %s", settings.content_dir, ", ".join(repository.ids()))
    return True


def install_reload_signal(loop: asyncio.AbstractEventLoop) -> Callable[[], None]:
    """Reload content on SIGHUP. Returns a function that removes the handler.

    The handler is registered on the event loop, so the reload runs on the loop
    thread and never races a request handler. Platforms without SIGHUP and
    loops outside the main thread cannot register signal handlers; both cases
    are logged and the server keeps running without the reload signal.
    """
    reload_signal = getattr(signal, "SIGHUP", None)
    if reload_signal is None:
        logger.warning("Content reload signal is not available on this platform.")
        return lambda: None
    try:
        loop.add_signal_handler(reload_signal, reload_content)
    except (NotImplementedError, RuntimeError, ValueError) as error:
        logger.warning("Content reload signal could not be installed: %s", error)
        return lambda: None
    return lambda: loop.remove_signal_handler(reload_signal)


def _ensure_logging() -> None:
    """Show reload results on the console when nothing else configured logging.

    uvicorn only configures its own loggers, so without this a successful
    reload would be silent and only errors would reach the console.
    """
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
    logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _ensure_logging()
    remove_handler = install_reload_signal(asyncio.get_running_loop())
    try:
        yield
    finally:
        remove_handler()


app = FastAPI(title="AskHarbor API", version=get_version(), lifespan=lifespan)

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
