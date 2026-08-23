from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import settings


password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def create_access_token(
    *,
    user_id: str,
    organization_id: str | None = None,
    auth_version: int = 1,
) -> str:
    return _create_session_token(
        user_id=user_id,
        organization_id=organization_id,
        auth_version=auth_version,
        token_type="access",
        expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=settings.access_token_minutes),
    )


def create_refresh_token(
    *,
    user_id: str,
    organization_id: str | None = None,
    auth_version: int = 1,
) -> str:
    return _create_session_token(
        user_id=user_id,
        organization_id=organization_id,
        auth_version=auth_version,
        token_type="refresh",
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.refresh_token_days),
    )


def _create_session_token(
    *,
    user_id: str,
    organization_id: str | None,
    auth_version: int,
    token_type: str,
    expires_at: datetime,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "org": organization_id,
        "ver": auth_version,
        "typ": token_type,
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return _decode_session_token(token, expected_type="access")


def decode_refresh_token(token: str) -> dict:
    return _decode_session_token(token, expected_type="refresh")


def _decode_session_token(token: str, *, expected_type: str) -> dict:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    # Access tokens issued before refresh support had no explicit type. Keep
    # those sessions compatible, but never allow them to act as refresh tokens.
    token_type = payload.get("typ", "access")
    if token_type != expected_type:
        raise jwt.InvalidTokenError("Unexpected session token type")
    return payload
