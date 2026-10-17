from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_current_user, get_db
from app.models.password_reset import PasswordResetToken
from app.models.preferences import UserPreference
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services import security
from app.services.email import send_email

log = logging.getLogger("mark_liv.auth")
router = APIRouter(tags=["auth"])

_RESET_TTL_MINUTES = 30


def _token_response(user_id: str) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        access_token=security.create_access_token(user_id),
        refresh_token=security.create_refresh_token(user_id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    user = User(
        email=body.email.lower(),
        password_hash=security.hash_password(body.password),
        display_name=body.display_name.strip(),
    )
    user.preferences = UserPreference()
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists.",
        )
    await db.refresh(user)
    return _token_response(user.id)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    # Verify even when the user is missing to keep timing roughly constant.
    password_hash = user.password_hash if user else security.hash_password("x")
    if not security.verify_password(password_hash, body.password) or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled.")
    return _token_response(user.id)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    try:
        payload = security.decode_token(body.refresh_token, expected_type="refresh")
    except security.TokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")
    user = await db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")
    return _token_response(user.id)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/logout", status_code=204)
async def logout(user: User = Depends(get_current_user)) -> None:
    # JWTs are stateless. A production deployment can add a denylist keyed by
    # the token `jti`; the client simply discards its tokens here.
    return None


@router.post("/password-reset/request", status_code=202)
async def request_password_reset(
    body: PasswordResetRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Always returns 202 so the endpoint cannot be used to enumerate accounts."""
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if user is not None:
        raw = security.new_reset_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=security.hash_reset_token(raw),
                expires_at=datetime.now(timezone.utc)
                + timedelta(minutes=_RESET_TTL_MINUTES),
            )
        )
        await db.commit()
        link = f"{get_settings().web_app_url}/reset-password?token={raw}"
        try:
            send_email(
                user.email,
                "Reset your MARK LIV password",
                f"Use this link to reset your password:\n\n{link}\n\n"
                f"It expires in {_RESET_TTL_MINUTES} minutes.",
            )
        except Exception:  # noqa: BLE001 - never leak delivery failure to client
            log.exception("password reset email failed to send")
    return {"status": "accepted"}


@router.post("/password-reset/confirm", status_code=200)
async def confirm_password_reset(
    body: PasswordResetConfirm, db: AsyncSession = Depends(get_db)
) -> dict:
    token_hash = security.hash_reset_token(body.token)
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token.")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired token.")

    user = await db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token.")
    user.password_hash = security.hash_password(body.new_password)
    row.used_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "password updated"}
