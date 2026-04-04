from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration loaded from environment variables or .env file.
    Priority: env vars > Docker secrets (/run/secrets) > .env file.
    No hardcoded credentials anywhere.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        secrets_dir="/run/secrets",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://scheduler:changeme@localhost:5432/scheduling_db",
        description="Async SQLAlchemy DSN (asyncpg driver)",
    )
    SYNC_DATABASE_URL: str = Field(
        default="postgresql+psycopg2://scheduler:changeme@localhost:5432/scheduling_db",
        description="Sync SQLAlchemy DSN for Alembic migrations",
    )

    # ── Redis / Celery ────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = Field(
        default="CHANGE_ME_IN_PRODUCTION",
        min_length=16,
        description="Secret key for signing tokens. MUST be overridden in production.",
    )

    # ── Solver ────────────────────────────────────────────────────────────────
    SOLVER_TIME_LIMIT: int = Field(default=300, ge=10, le=3600)
    SOLVER_GAP_TOLERANCE: float = Field(default=0.05, ge=0.0, le=1.0)
    DEFAULT_SOLVER: str = "pulp_cbc"

    # ── Penalty weights (defaults from MM.lng DATA section) ───────────────────
    PENALTY1_DEFAULT: float = Field(default=2.0, ge=0.0)
    PENALTY2_DEFAULT: float = Field(default=1.0, ge=0.0)

    # ── Application ───────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return json.loads(v)
        return v


# Singleton — imported everywhere to avoid re-parsing .env
settings = Settings()
