import base64
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. APP_ENV defaults to production, which disables local login."""

    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "production"
    database_url: str
    migration_database_url: str
    session_secret: str
    contact_encryption_key: str
    cors_origins: str = "http://127.0.0.1:3000"
    local_token_ttl_seconds: int = Field(default=8 * 60 * 60)
    allow_fixture_ledger_settlement: bool = False
    payment_simulator: str = "unset"
    step_up_max_age_seconds: int = 0
    media_scanner: str = "unset"
    media_root: str = "var/media"

    @field_validator("app_env")
    @classmethod
    def known_environment(cls, value: str) -> str:
        if value not in {"development", "test", "production"}:
            raise ValueError("app_env must be development, test, or production")
        return value

    @field_validator("session_secret")
    @classmethod
    def secret_length(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("session_secret must be at least 32 characters")
        return value

    @field_validator("contact_encryption_key")
    @classmethod
    def encryption_key(cls, value: str) -> str:
        try:
            raw = base64.b64decode(value, validate=True)
        except Exception as exc:
            raise ValueError("contact_encryption_key must be standard base64") from exc
        if len(raw) != 32:
            raise ValueError("contact_encryption_key must decode to 32 bytes")
        return value

    @field_validator("local_token_ttl_seconds")
    @classmethod
    def token_ttl(cls, value: int) -> int:
        if not 60 <= value <= 24 * 60 * 60:
            raise ValueError("local_token_ttl_seconds must be between 60 and 86400")
        return value

    @property
    def allows_local_auth(self) -> bool:
        return self.app_env in {"development", "test"}

    @property
    def fixture_ledger_settlement_allowed(self) -> bool:
        return False

    @property
    def payment_simulator_enabled(self) -> bool:
        return self.allows_local_auth and self.payment_simulator == "enabled"

    @property
    def fixture_media_scanner_allowed(self) -> bool:
        return self.allows_local_auth and self.media_scanner == "fixture"

    @property
    def contact_key_bytes(self) -> bytes:
        return base64.b64decode(self.contact_encryption_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
