"""Declarative base and shared column helpers."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    """A DB-agnostic string primary key (UUID4 hex)."""
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    # A Python-side default (microsecond precision) is used for ORM inserts so
    # message ordering within one second is deterministic — SQLite's
    # CURRENT_TIMESTAMP only has second resolution. server_default keeps raw
    # SQL inserts working too.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )
