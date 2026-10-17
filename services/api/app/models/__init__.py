"""Import every model so `Base.metadata` is complete.

Alembic autogenerate and `create_all` both rely on this module having been
imported. Add new models here.
"""
from app.database.base import Base
from app.models.conversation import Conversation, Message
from app.models.device import ActionHistory, DevicePermission, PairedDevice
from app.models.password_reset import PasswordResetToken
from app.models.preferences import UserPreference
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Conversation",
    "Message",
    "UserPreference",
    "PairedDevice",
    "DevicePermission",
    "ActionHistory",
    "PasswordResetToken",
]
