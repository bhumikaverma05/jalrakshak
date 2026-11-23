"""Environment-backed application settings."""

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    app_name: str = "JalRakshak API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    database_url: str = "postgresql+psycopg://jalrakshak:change-me@localhost:5433/jalrakshak_db"
    app_env: str = "development"
    database_echo: bool = False
    database_pool_size: int = Field(default=5, ge=1, le=64)
    database_max_overflow: int = Field(default=10, ge=0, le=128)
    database_connect_timeout: int = Field(default=5, ge=1, le=60)
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value or not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use the postgresql+psycopg:// scheme")
        parsed = make_url(value)
        if not parsed.username or not parsed.host or not parsed.database:
            raise ValueError("DATABASE_URL must include a database user, host, and database name")
        return value

    @model_validator(mode="after")
    def validate_production_database_credentials(self) -> "Settings":
        if self.app_env.casefold() == "production":
            if make_url(self.database_url).password in {None, "", "change-me", "replace-me"}:
                raise ValueError("Production DATABASE_URL must use a non-placeholder password")
            if len(self.secret_key) < 32 or self.secret_key.casefold().startswith(
                ("replace-", "change-", "dev-only")
            ):
                raise ValueError(
                    "Production SECRET_KEY must be a private key of at least 32 characters"
                )
        if self.jwt_algorithm != "HS256":
            raise ValueError("JWT_ALGORITHM must be HS256")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings object for the running process."""
    return Settings()
