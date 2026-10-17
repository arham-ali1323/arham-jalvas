"""Shared FastAPI dependencies."""
from __future__ import annotations

from typing import AsyncIterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_sessionmaker
from app.models.user import User
from app.services import security

_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or not credentials.credentials:
        raise auth_error
    try:
        payload = security.decode_token(
            credentials.credentials, expected_type="access"
        )
    except security.TokenError:
        raise auth_error

    user = await db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise auth_error
    return user
