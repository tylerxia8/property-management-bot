import base64
import re
from functools import lru_cache
from uuid import UUID

from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
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
    approval_ttl_hours: int = 0
    webhook_secret: str = ""
    webhook_replay_seconds: int = 300
    media_scanner: str = "unset"
    media_root: str = "var/media"
    openai_api_key: SecretStr = SecretStr("")
    maintenance_history_path: str = ""
    maintenance_history_organization_id: UUID | None = None
    demo_fixture: str = "unset"
    stripe_secret_key: SecretStr = SecretStr("")
    stripe_webhook_secret: SecretStr = SecretStr("")
    stripe_api_version: str = "2025-02-24.acacia"
    stripe_public_url: str = "http://localhost:3000"
    stripe_worker_enabled: bool = False
    twilio_account_sid: str = ""
    twilio_auth_token: SecretStr = SecretStr("")
    twilio_phone_number: str = ""
    twilio_public_url: str = ""
    twilio_organization_id: UUID | None = None
    twilio_service_user_id: UUID | None = None
    twilio_maintenance_notify_number: str = ""
    maintenance_backup_notify_number: str = ""
    maintenance_manager_notify_number: str = ""
    maintenance_urgent_ack_minutes: int = Field(default=10, ge=1, le=60)

    @field_validator("twilio_maintenance_notify_number", "maintenance_backup_notify_number", "maintenance_manager_notify_number")
    @classmethod
    def maintenance_notification_number(cls, value):
        if value and not re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
            raise ValueError("Maintenance notification number must use E.164 format")
        return value

    @field_validator("twilio_organization_id", "twilio_service_user_id", "maintenance_history_organization_id", mode="before")
    @classmethod
    def optional_service_identity(cls, value):
        return None if value == "" else value

    @property
    def twilio_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token.get_secret_value() and self.twilio_phone_number and self.twilio_public_url and self.twilio_organization_id and self.twilio_service_user_id)

    @model_validator(mode="after")
    def maintenance_history_configuration(self):
        if bool(self.maintenance_history_path) != bool(self.maintenance_history_organization_id):
            raise ValueError("Maintenance history requires a private index path and organization scope")
        return self

    @model_validator(mode="after")
    def twilio_configuration(self):
        configured = (self.twilio_account_sid, self.twilio_auth_token.get_secret_value(), self.twilio_phone_number, self.twilio_public_url, self.twilio_organization_id, self.twilio_service_user_id)
        if any(configured) and not all(configured):
            raise ValueError("Twilio requires account credentials, a phone number, a public origin, and an organization and service user")
        if not any(configured):
            return self
        if not re.fullmatch(r"AC[0-9a-fA-F]{32}", self.twilio_account_sid):
            raise ValueError("Twilio account SID is invalid")
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", self.twilio_phone_number):
            raise ValueError("Twilio phone number must use E.164 format")
        if self.maintenance_manager_notify_number and self.maintenance_manager_notify_number == self.twilio_phone_number:
            raise ValueError("Maintenance manager number must differ from the intake line")
        if self.maintenance_backup_notify_number and self.maintenance_backup_notify_number == self.maintenance_manager_notify_number:
            raise ValueError("Maintenance backup must differ from the manager contact")
        if self.maintenance_backup_notify_number and self.maintenance_backup_notify_number == self.twilio_phone_number:
            raise ValueError("Maintenance backup number must differ from the intake line")
        if self.maintenance_backup_notify_number and self.maintenance_backup_notify_number == self.twilio_maintenance_notify_number:
            raise ValueError("Maintenance backup must differ from the primary contact")
        if self.twilio_maintenance_notify_number == self.twilio_phone_number:
            raise ValueError("Maintenance notification number must differ from the intake line")
        parsed = urlparse(self.twilio_public_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("Twilio public URL must be an HTTPS origin without credentials")
        self.twilio_public_url = self.twilio_public_url.rstrip("/")
        return self

    @field_validator("stripe_public_url")
    @classmethod
    def stripe_redirect_origin(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("stripe_public_url must be an origin without credentials")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}):
            raise ValueError("stripe_public_url must use HTTPS or local loopback")
        if not parsed.hostname:
            raise ValueError("stripe_public_url must include a hostname")
        return value.rstrip("/")

    @property
    def stripe_configured(self) -> bool:
        return self.allows_local_auth and self.stripe_secret_key.get_secret_value().startswith(("sk_test_", "rk_test_"))

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
    def database_name(self) -> str:
        return urlparse(self.database_url).path.rsplit("/", 1)[-1]

    @property
    def allows_demo_session(self) -> bool:
        migration_name = urlparse(self.migration_database_url).path.rsplit("/", 1)[-1]
        return (
            self.allows_local_auth
            and self.demo_fixture == "sample"
            and self.database_name == "grok_demo_sample"
            and migration_name == "grok_demo_sample"
        )

    @property
    def fixture_ledger_settlement_allowed(self) -> bool:
        return False

    @property
    def payment_simulator_enabled(self) -> bool:
        return self.allows_local_auth and self.payment_simulator == "enabled"

    @property
    def webhook_ingress_enabled(self) -> bool:
        return self.allows_local_auth and len(self.webhook_secret) >= 16

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
