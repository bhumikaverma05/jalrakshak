"""Registration, login, and current-user routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.domains.auth.dependencies import CurrentUser
from app.domains.auth.schemas import RegistrationRequest, TokenResponse, UserResponse
from app.domains.auth.security import create_access_token
from app.domains.auth.service import authenticate_user, register_user

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a citizen account",
)
def register(
    request: RegistrationRequest,
    session: Annotated[Session, Depends(get_session)],
) -> UserResponse:
    """Register a public citizen account; elevated roles require trusted provisioning."""
    try:
        user = register_user(session, request)
        if user is None:
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        session.flush()
        return UserResponse.model_validate(user)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Account service is unavailable") from None


@router.post(
    "/login", response_model=TokenResponse, summary="Log in and receive a JWT access token"
)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[Session, Depends(get_session)],
) -> TokenResponse:
    """Authenticate by email (OAuth2 form username field) and password."""
    try:
        user = authenticate_user(session, form.username, form.password)
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503, detail="Authentication service is unavailable"
        ) from None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        token = create_access_token(user.id)
    except RuntimeError:
        raise HTTPException(
            status_code=503, detail="Authentication service is unavailable"
        ) from None
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse, summary="Get the authenticated user profile")
def read_current_user(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
