"""Password hashing and signed access-token utilities."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hasher = PasswordHash.recommended()
_dummy_password_hash = password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    """Hash a password with the configured Argon2-backed recommended hasher."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a password, doing a dummy Argon2 check for unknown accounts."""
    if password_hash is None:
        password_hasher.verify(password, _dummy_password_hash)
        return False
    try:
        return password_hasher.verify(password, password_hash)
    except (ValueError, TypeError):
        password_hasher.verify(password, _dummy_password_hash)
        return False


def create_access_token(user_id: UUID) -> str:
    """Create an HS256 token whose subject is the database user UUID."""
    settings = get_settings()
    if len(settings.secret_key) < 32:
        raise RuntimeError("SECRET_KEY must contain at least 32 characters to issue access tokens")
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> UUID:
    """Validate signature and expiration, then return a valid UUID subject."""
    settings = get_settings()
    if len(settings.secret_key) < 32:
        raise RuntimeError(
            "SECRET_KEY must contain at least 32 characters to validate access tokens"
        )
    claims = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "iat", "sub"]},
    )
    subject = claims.get("sub")
    if not isinstance(subject, str):
        raise jwt.InvalidTokenError("Missing token subject")
    try:
        return UUID(subject)
    except ValueError as exc:
        raise jwt.InvalidTokenError("Invalid token subject") from exc
