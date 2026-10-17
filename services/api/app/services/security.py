"""Password hashing and JWT issuing/verification.

Passwords: Argon2id via argon2-cffi. Plaintext never leaves this module.
Tokens: short-lived access + long-lived refresh JWTs, signed with the app secret.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_settings

_hasher = PasswordHasher()

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """Raised when a JWT is missing, malformed, expired, or of the wrong type."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _create_token(subject: str, token_type: TokenType, expires: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str) -> str:
    settings = get_settings()
    return _create_token(
        subject, "access", timedelta(minutes=settings.access_token_expire_minutes)
    )


def create_refresh_token(subject: str) -> str:
    settings = get_settings()
    return _create_token(
        subject, "refresh", timedelta(days=settings.refresh_token_expire_days)
    )


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("invalid token") from exc
    if expected_type is not None and payload.get("type") != expected_type:
        raise TokenError("wrong token type")
    return payload


def hash_reset_token(token: str) -> str:
    """One-way hash for stored password-reset tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_reset_token() -> str:
    return secrets.token_urlsafe(32)
