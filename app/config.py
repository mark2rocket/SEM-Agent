"""Configuration management using Pydantic Settings."""

from typing import Optional
from pydantic import Field, field_validator, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # FastAPI
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    debug: bool = Field(default=False)
    environment: str = Field(default="production")

    # Database
    database_url: str = Field(...)
    database_pool_size: int = Field(default=20)
    database_max_overflow: int = Field(default=10)

    # Redis
    redis_url: str = Field(...)

    # Celery (defaults to Redis URL if not set)
    celery_broker_url: Optional[str] = Field(default=None)
    celery_result_backend: Optional[str] = Field(default=None)

    # Slack
    slack_client_id: str = Field(...)
    slack_client_secret: str = Field(...)
    slack_signing_secret: str = Field(...)
    slack_app_token: Optional[str] = Field(default=None)
    slack_redirect_uri: str = Field(default="http://localhost:8000/oauth/slack/callback")
    slack_bot_token: str = Field(default="")
    slack_alert_channel: str = Field(default="#alerts")

    # Google OAuth
    google_client_id: str = Field(...)
    google_client_secret: str = Field(...)
    google_redirect_uri: str = Field(...)

    # Google Ads
    google_developer_token: str = Field(...)
    google_login_customer_id: str = Field(...)

    # Gemini AI
    gemini_api_key: str = Field(...)
    gemini_default_model: str = Field(
        default="gemini-2.0-flash",
        validation_alias=AliasChoices("gemini_default_model", "gemini_model")
    )
    gemini_pro_model: str = Field(default="gemini-1.5-pro")
    gemini_flash_rpm: int = Field(default=60)
    gemini_pro_rpm: int = Field(default=10)

    # Security
    token_encryption_key: str = Field(...)
    secret_key: str = Field(...)
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)

    # Celery timezone
    celery_timezone: str = Field(default="Asia/Seoul")

    # Monitoring
    sentry_dsn: Optional[str] = Field(default=None)
    log_level: str = Field(default="INFO")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v_upper

    def __init__(self, **data):
        super().__init__(**data)
        # Set Celery URLs to Redis URL if not explicitly provided
        if not self.celery_broker_url:
            self.celery_broker_url = self.redis_url
        if not self.celery_result_backend:
            self.celery_result_backend = self.redis_url

    @property
    def database_url_sync(self) -> str:
        """Synchronous database URL for SQLAlchemy."""
        return self.database_url.replace("postgresql://", "postgresql+psycopg2://")

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"


# Global settings instance
settings = Settings()
