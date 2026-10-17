"""Application settings for the MARK LIV backend.

All configuration comes from the environment (or a `.env` file next to this
service). Nothing is hardcoded and no secret has a usable default in production.
"""
from __future__ import annotations

import secrets
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── General ──────────────────────────────────────────────────────────────
    app_name: str = "MARK LIV API"
    environment: str = Field(default="development")  # development | production
    debug: bool = False

    # ── Database ─────────────────────────────────────────────────────────────
    # PostgreSQL in production, SQLite for local development and tests.
    #   postgresql+asyncpg://user:pass@host:5432/mark_liv
    #   sqlite+aiosqlite:///./mark_liv_dev.db
    database_url: str = "sqlite+aiosqlite:///./mark_liv_dev.db"

    # ── Authentication ──────────────────────────────────────────────────────
    # MUST be set in production. In development an ephemeral secret is generated
    # at startup so the service runs out of the box; tokens then do not survive a
    # restart, which is the correct behaviour for a throwaway secret.
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # ── AI provider ──────────────────────────────────────────────────────────
    # "gemini" uses the Google GenAI SDK. "none" disables chat (returns 503).
    ai_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_text_model: str = "gemini-2.5-flash"

    # ── Live voice ───────────────────────────────────────────────────────────
    # The real-time (speech-to-speech) model. The permanent API key stays on the
    # server; the browser only ever receives PCM and control frames.
    gemini_live_model: str = "models/gemini-3.1-flash-live-preview"
    # Default prebuilt voice. Clients may pick a different one per session from
    # the server-approved list in `app/services/live.py` (same list the desktop
    # uses, so both companions sound like the same assistant).
    live_voice_name: str = "Charon"
    # A live session's system instruction. Kept server-side so a client cannot
    # inject an arbitrary persona; an empty value falls back to the built-in one.
    live_system_instruction: str = ""
    # Browsers cannot set an Authorization header on a WebSocket, so they
    # exchange their session for a short-lived, single-use ticket. Seconds.
    live_ticket_ttl_seconds: int = 60
    # Per-user guards so a single account cannot exhaust the shared Gemini quota.
    live_max_concurrent_sessions: int = 4
    live_connect_attempts_per_minute: int = 12

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Comma-separated allowlist. Never "*" in production.
    cors_origins: str = "http://localhost:3000"

    # ── Password reset email ─────────────────────────────────────────────────
    # "console" logs the reset link (development only).
    # "smtp" sends real mail and requires the smtp_* settings below.
    email_backend: str = "console"  # console | smtp
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@mark-liv.local"
    smtp_use_tls: bool = True
    # Base URL of the web app, used to build the password-reset link.
    web_app_url: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    def model_post_init(self, __context: object) -> None:  # noqa: D401
        if not self.jwt_secret:
            if self.is_production:
                raise ValueError(
                    "JWT_SECRET must be set when ENVIRONMENT=production"
                )
            self.jwt_secret = secrets.token_urlsafe(48)
        if self.is_production:
            if len(self.jwt_secret.strip()) < 32:
                raise ValueError(
                    "JWT_SECRET must contain at least 32 characters in production"
                )
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError(
                    "DATABASE_URL must use postgresql+asyncpg in production"
                )
            if "*" in self.cors_origin_list:
                raise ValueError("CORS_ORIGINS must not contain '*' in production")
            if self.email_backend.lower() != "smtp":
                raise ValueError(
                    "EMAIL_BACKEND=smtp is required when ENVIRONMENT=production"
                )
            if not self.smtp_host.strip():
                raise ValueError("SMTP_HOST must be set when EMAIL_BACKEND=smtp")
            sender_domain = self.smtp_from.rpartition("@")[2].lower()
            if not sender_domain or sender_domain.endswith(".local"):
                raise ValueError(
                    "SMTP_FROM must use a non-local sender address in production"
                )
            if bool(self.smtp_username) != bool(self.smtp_password):
                raise ValueError(
                    "SMTP_USERNAME and SMTP_PASSWORD must be set together"
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()
