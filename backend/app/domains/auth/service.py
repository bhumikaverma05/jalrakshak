"""Authentication and account services."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import User
from app.domains.auth.schemas import RegistrationRequest
from app.domains.auth.security import hash_password, verify_password


def register_user(session: Session, request: RegistrationRequest) -> User | None:
    """Create a citizen account; return None when a case-insensitive email exists."""
    normalized_email = request.email.casefold()
    existing = session.scalar(select(User.id).where(func.lower(User.email) == normalized_email))
    if existing is not None:
        return None

    user = User(
        email=normalized_email,
        full_name=request.full_name,
        password_hash=hash_password(request.password),
        role="citizen",
    )
    try:
        with session.begin_nested():
            session.add(user)
            session.flush()
    except IntegrityError:
        # The unique functional index is the final guard against concurrent requests.
        return None
    return user


def authenticate_user(session: Session, email: str, password: str) -> User | None:
    """Return an active user only after verifying credentials; hide account state."""
    normalized_email = email.strip().casefold()
    user = session.scalar(select(User).where(func.lower(User.email) == normalized_email))
    if user is None:
        verify_password(password, None)
        return None
    if not verify_password(password, user.password_hash) or not user.is_active:
        return None
    return user
