from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    model_config = SettingsConfigDict(env_prefix="ASKHARBOR_", env_file=".env")

    @field_validator("allowed_origins")
    @classmethod
    def refuse_blank_origins(cls, value: str) -> str:
        if not _parse_origins(value):
            raise ValueError(_EMPTY_ORIGINS_MESSAGE)
        return value

    @property
    def cors_origins(self) -> list[str]:
        return _parse_origins(self.allowed_origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
