from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_EMPTY_ORIGINS_MESSAGE = (
    "ASKHARBOR_ALLOWED_ORIGINS is set but contains no origins, so every browser "
    "request would be blocked. Set it to a comma separated list of exact origins, "
    "for example ASKHARBOR_ALLOWED_ORIGINS=https://www.example.com,https://app.example.com "
    "or ASKHARBOR_ALLOWED_ORIGINS=* to allow any origin during local development. "
    "To use the default of *, remove the variable from the environment and from "
    "server/.env instead of leaving it empty."
)


class Settings(BaseSettings):
    allowed_origins: str = "*"

    model_config = SettingsConfigDict(env_prefix="ASKHARBOR_", env_file=".env")

    @field_validator("allowed_origins")
    @classmethod
    def refuse_blank_origins(cls, value: str) -> str:
        if not [origin for origin in value.split(",") if origin.strip()]:
            raise ValueError(_EMPTY_ORIGINS_MESSAGE)
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
