from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class UserPreference(Base, TimestampMixin):
    """One settings row per user. Free-form extras live in `extra`."""

    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    theme: Mapped[str] = mapped_column(String(16), default="dark")  # dark | light
    voice_name: Mapped[str] = mapped_column(String(64), default="Charon")
    model: Mapped[str] = mapped_column(String(120), default="")
    ai_provider: Mapped[str] = mapped_column(String(32), default="gemini")
    input_device: Mapped[str] = mapped_column(String(200), default="")
    output_device: Mapped[str] = mapped_column(String(200), default="")
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    user = relationship("User", back_populates="preferences")
