from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, new_id


class PairedDevice(Base, TimestampMixin):
    """A desktop companion that a user has authorised."""

    __tablename__ = "paired_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), default="MARK LIV Desktop")
    platform: Mapped[str] = mapped_column(String(40), default="")
    fingerprint: Mapped[str] = mapped_column(String(128), default="")
    # Hash of the long-lived device credential — never the credential itself.
    token_hash: Mapped[str] = mapped_column(String(255), default="")
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User", back_populates="devices")
    permissions = relationship(
        "DevicePermission", back_populates="device", cascade="all, delete-orphan"
    )


class DevicePermission(Base):
    """A single scoped capability granted to a paired device.

    Examples of `permission`: "open_app", "browser.navigate", "files.read".
    """

    __tablename__ = "device_permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("paired_devices.id", ondelete="CASCADE"), index=True
    )
    permission: Mapped[str] = mapped_column(String(100), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    device = relationship("PairedDevice", back_populates="permissions")


class ActionHistory(Base, TimestampMixin):
    """Audit log of every command routed to a paired device."""

    __tablename__ = "action_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("paired_devices.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    # pending | approved | denied | success | error
    status: Mapped[str] = mapped_column(String(20), default="pending")
    result: Mapped[str] = mapped_column(String(2000), default="")
