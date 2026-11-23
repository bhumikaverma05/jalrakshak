"""Reusable bearer authentication and role authorization dependencies."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import User
from app.db.session import get_session
from app.domains.auth.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().api_v1_prefix}/auth/login",
    scheme_name="JWT Bearer",
)
_invalid_credentials = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    """Validate JWT claims and load an active user from the database."""
    try:
        user_id: UUID = decode_access_token(token)
    except (jwt.InvalidTokenError, RuntimeError):
        raise _invalid_credentials from None
    user = session.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise _invalid_credentials
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str) -> Callable[..., User]:
    """Build a reusable dependency that admits only the listed stored roles."""
    if not roles:
        raise ValueError("At least one role is required")

    def role_dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    role_dependency.__name__ = f"require_{'_or_'.join(roles)}"
    return role_dependency


require_citizen = require_roles("citizen")
require_engineer = require_roles("engineer")
require_officer = require_roles("officer")
require_administrator = require_roles("administrator")
