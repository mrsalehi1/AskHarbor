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
    # Where the public bots are served from: JSON files (default) or PostgreSQL.
    content_source: Literal["files", "database"] = "files"
    # SQLAlchemy URL for PostgreSQL, e.g. postgresql+psycopg://user:pass@host/db.
    database_url: str | None = None

    model_config = SettingsConfigDict(env_prefix="ASKHARBOR_", env_file=".env")

    @model_validator(mode="after")
    def database_mode_needs_a_url(self) -> "Settings":
        if self.content_source == "database" and not (self.database_url or "").strip():
            raise ValueError(_DATABASE_URL_REQUIRED_MESSAGE)
        return self

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
