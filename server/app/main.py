import asyncio
import logging
import signal
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

from .auth_routes import AuthService, build_router
from .config import get_settings
from .content import ContentLoadError, load_content_directory
from .cors import PublicCORSMiddleware
from .models import BotConfig, ChatOption, MessageRequest, MessageResponse
from .rate_limit import FixedWindowRateLimiter
from .repository import BotRepository
from .version import get_version

logger = logging.getLogger("askharbor")

settings = get_settings()

ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "alembic"


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


def _database_content_source():
    """Serve bots from PostgreSQL, refusing to start on an unmigrated database."""
    from .db import get_engine, session_factory
    from .storage import DatabaseContentSource, assert_database_ready

    assert settings.database_url is not None  # enforced by Settings validation
    assert_database_ready(get_engine(settings.database_url), ALEMBIC_DIR)
    return DatabaseContentSource(session_factory(settings.database_url))


# In file mode this is the in-memory repository with SIGHUP reload. In database
# mode it reads live, so edits are visible without any reload, every worker
# sees the same content, and the endpoints below are identical in both modes.
repository = (
    _database_content_source() if settings.content_source == "database"
    else _load_startup_content()
)


def reload_content() -> bool:
    """Reload every bot from the content directory and swap the set atomically.

    File mode only: the new set replaces the old one when every file validates,
    otherwise the problems are logged and the loaded bots keep being served.
    Database mode reads live, so the signal only logs a note. Returns True when
    a swap happened.
    """
    if settings.content_source == "database":
        logger.info("Content reload signal ignored: database mode reads live.")
        return False
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


def _session_factory():
    """Database sessions for accounts, or None when no database is configured."""
    if not settings.accounts_enabled:
        return None
    from .db import session_factory

    assert settings.database_url is not None
    return session_factory(settings.database_url)


auth_service = AuthService(settings, _session_factory())


def prepare_accounts() -> None:
    """Check the database and create the bootstrap admin once.

    Runs at startup in every worker. Each worker checks that the migrations are
    current, then runs the bootstrap inside a database lock so exactly one of
    them creates the first admin and the rest see it and skip.
    """
    if auth_service.factory is None:
        logger.info("Accounts disabled: ASKHARBOR_DATABASE_URL is not set.")
        return
    from .auth import bootstrap_admin, purge_expired_sessions
    from .storage import assert_database_ready

    assert_database_ready(auth_service.factory.kw["bind"], ALEMBIC_DIR)
    with auth_service.factory() as db, db.begin():
        bootstrap_admin(db, settings)
        purged = purge_expired_sessions(db)
    if purged:
        logger.info("Removed %d expired login session(s).", purged)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _ensure_logging()
    try:
        prepare_accounts()
    except SystemExit as error:
        # Inside the lifespan a SystemExit would be swallowed; make uvicorn fail loudly.
        raise RuntimeError(str(error)) from None
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
# Cross-origin access is for the widget's public routes only; account routes
# are same-origin by design.
app.add_middleware(PublicCORSMiddleware, allow_origins=settings.cors_origins)
app.include_router(build_router(auth_service))


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
