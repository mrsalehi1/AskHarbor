from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Bot content files ship next to the package so a fresh checkout starts without configuration.
DEFAULT_CONTENT_DIR = Path(__file__).resolve().parents[1] / "content"

_EMPTY_CONTENT_DIR_MESSAGE = (
    "ASKHARBOR_CONTENT_DIR is set but empty. Set it to the directory holding the bot "
    "content files, one JSON file per bot, or remove the variable from the environment and "
    "from server/.env to use the default server/content directory."
)

# Local development account. Documented in the README; production must replace it.
DEFAULT_BOOTSTRAP_USERNAME = "admin"
DEFAULT_BOOTSTRAP_PASSWORD = "ChangeMeLocal123!"
MIN_PASSWORD_LENGTH = 12

_PRODUCTION_DEFAULT_PASSWORD_MESSAGE = (
    "ASKHARBOR_ENV is 'production' but ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD is the documented "
    "local development password. Set ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD to a secret of at "
    f"least {MIN_PASSWORD_LENGTH} characters (and ASKHARBOR_BOOTSTRAP_ADMIN_USERNAME if you want "
    "a different admin name). It is only used once, when the users table is empty."
)
_PRODUCTION_SHORT_PASSWORD_MESSAGE = (
    "ASKHARBOR_ENV is 'production' but ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD is shorter than "
    f"{MIN_PASSWORD_LENGTH} characters."
)
_PRODUCTION_INSECURE_COOKIE_MESSAGE = (
    "ASKHARBOR_ENV is 'production' but ASKHARBOR_COOKIE_SECURE is false. Session cookies must "
    "only travel over HTTPS in production; remove the variable or set it to true."
)

_DATABASE_URL_REQUIRED_MESSAGE = (
    "ASKHARBOR_CONTENT_SOURCE is 'database' but ASKHARBOR_DATABASE_URL is not set. "
    "Set it to a PostgreSQL URL such as "
    "postgresql+psycopg://askharbor:askharbor@127.0.0.1:5432/askharbor, "
    "or set ASKHARBOR_CONTENT_SOURCE=files to serve bots from the content directory."
)

_EMPTY_ORIGINS_MESSAGE = (
    "ASKHARBOR_ALLOWED_ORIGINS is set but contains no origins, so every browser "
    "request would be blocked. Set it to a comma separated list of exact origins, "
    "for example ASKHARBOR_ALLOWED_ORIGINS=https://www.example.com,https://app.example.com "
    "or ASKHARBOR_ALLOWED_ORIGINS=* to allow any origin during local development. "
    "To use the default of *, remove the variable from the environment and from "
    "server/.env instead of leaving it empty."
)


def _parse_origins(value: str) -> list[str]:
    """Split a comma separated origin list, trimming spaces and trailing slashes.

    Browsers send the Origin header without a trailing slash, so a configured
    value like https://example.com/ must match https://example.com.
    """
    origins = []
    for entry in value.split(","):
        origin = entry.strip().rstrip("/")
        if origin:
            origins.append(origin)
    return origins


class Settings(BaseSettings):
    allowed_origins: str = "*"
    # Requests per client allowed on POST /messages within one window. 0 disables the limit.
    message_rate_limit: int = Field(default=30, ge=0)
    message_rate_window_seconds: int = Field(default=60, ge=1)
    # Directory of bot content files, one JSON file per bot.
    content_dir: Path = Field(default=DEFAULT_CONTENT_DIR)
    # Where the public bots are served from. "auto" (default) means PostgreSQL
    # when ASKHARBOR_DATABASE_URL is set and the JSON content files otherwise.
    content_source: Literal["auto", "files", "database"] = "auto"
    # Public base URL of this API as browsers reach it, used in the embed snippet
    # shown to site owners. Defaults to the URL of the request that asks.
    public_url: str | None = None
    # Load the fictional sample bots into an empty database at first start.
    seed_sample_content: bool = True
    # Built widget output served at /admin (admin panel, editor and askharbor.js).
    admin_dist: Path = Field(default=Path(__file__).resolve().parents[2] / "widget" / "dist")
    # SQLAlchemy URL for PostgreSQL, e.g. postgresql+psycopg://user:pass@host/db.
    # Accounts and login are available whenever this is set, in either content mode.
    database_url: str | None = None

    # "development" accepts the documented local admin account; "production" refuses it.
    env: Literal["development", "production"] = "development"
    # Created once, inside a database lock, when the users table is empty.
    bootstrap_admin_username: str = DEFAULT_BOOTSTRAP_USERNAME
    bootstrap_admin_password: str = DEFAULT_BOOTSTRAP_PASSWORD
    # Login sessions are stored in the database and expire after this many hours.
    session_hours: int = Field(default=12, ge=1, le=24 * 30)
    # Send the session cookie only over HTTPS. Set to false for plain http://127.0.0.1 dev.
    cookie_secure: bool = True
    # Failed login attempts allowed per client address and per username within one window.
    login_rate_limit: int = Field(default=5, ge=0)
    login_rate_window_seconds: int = Field(default=300, ge=1)

    model_config = SettingsConfigDict(env_prefix="ASKHARBOR_", env_file=".env")

    @model_validator(mode="after")
    def database_mode_needs_a_url(self) -> "Settings":
        if self.content_source == "database" and not (self.database_url or "").strip():
            raise ValueError(_DATABASE_URL_REQUIRED_MESSAGE)
        return self

    @property
    def resolved_content_source(self) -> Literal["files", "database"]:
        if self.content_source == "auto":
            return "database" if self.accounts_enabled else "files"
        return self.content_source

    @model_validator(mode="after")
    def production_refuses_development_defaults(self) -> "Settings":
        if self.env != "production":
            return self
        if not self.cookie_secure:
            raise ValueError(_PRODUCTION_INSECURE_COOKIE_MESSAGE)
        if self.accounts_enabled:
            if self.bootstrap_admin_password == DEFAULT_BOOTSTRAP_PASSWORD:
                raise ValueError(_PRODUCTION_DEFAULT_PASSWORD_MESSAGE)
            if len(self.bootstrap_admin_password) < MIN_PASSWORD_LENGTH:
                raise ValueError(_PRODUCTION_SHORT_PASSWORD_MESSAGE)
        return self

    @property
    def accounts_enabled(self) -> bool:
        return bool((self.database_url or "").strip())

    @field_validator("allowed_origins")
    @classmethod
    def refuse_blank_origins(cls, value: str) -> str:
        if not _parse_origins(value):
            raise ValueError(_EMPTY_ORIGINS_MESSAGE)
        return value

    @field_validator("content_dir", mode="before")
    @classmethod
    def refuse_blank_content_dir(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError(_EMPTY_CONTENT_DIR_MESSAGE)
        return value

    @property
    def cors_origins(self) -> list[str]:
        return _parse_origins(self.allowed_origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
