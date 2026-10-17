from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, new_id


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    # Argon2id hash. The plaintext password is never stored anywhere.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    conversations = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    messages = relationship(
        "Message", back_populates="user", cascade="all, delete-orphan"
    )
    preferences = relationship(
        "UserPreference",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    devices = relationship(
        "PairedDevice", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User {self.id} {self.email}>"
