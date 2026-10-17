"""Async engine and session factory.

Created lazily and cached so tests can point `DATABASE_URL` at SQLite before the
first use without importing anything at module load.
"""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    kwargs: dict = {"echo": settings.debug, "future": True}
    if not settings.database_url.startswith("sqlite"):
        # SQLite (aiosqlite) does not support pool_pre_ping in the same way.
        kwargs["pool_pre_ping"] = True
    return create_async_engine(settings.database_url, **kwargs)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(), class_=AsyncSession, expire_on_commit=False
    )
