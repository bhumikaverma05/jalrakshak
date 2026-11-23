"""Authentication, JWT, authorization, and API contract tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from app.domains.auth.dependencies import (
    require_administrator,
    require_citizen,
    require_engineer,
    require_officer,
    require_roles,
)
from app.domains.auth.security import create_access_token, hash_password, verify_password
from app.main import app

VALID_PASSWORD = "Stronger-Passphrase-2026!"


def _seed_user(session: Session, role: str = "citizen", active: bool = True) -> User:
    user = User(
        email=f"{uuid4()}@example.com",
        full_name="API Test User",
        password_hash=hash_password(VALID_PASSWORD),
        role=role,
        is_active=active,
    )
    session.add(user)
    session.flush()
    return user


@pytest.fixture
def api_client(db_session: Session):
    from app.db.session import get_session

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_registration_hashes_password_and_returns_safe_profile(api_client, db_session):
    response = api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "New.User@example.com",
            "full_name": "  New User  ",
            "password": VALID_PASSWORD,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new.user@example.com"
    assert body["full_name"] == "New User"
    assert body["role"] == "citizen"
    assert "password" not in body and "password_hash" not in body
    user = db_session.scalar(select(User).where(User.email == body["email"]))
    assert user is not None
    assert user.password_hash != VALID_PASSWORD
    assert verify_password(VALID_PASSWORD, user.password_hash)


def test_duplicate_email_registration_is_case_insensitive(api_client):
    first = api_client.post(
        "/api/v1/auth/register",
        json={"email": "duplicate@example.com", "full_name": "First", "password": VALID_PASSWORD},
    )
    second = api_client.post(
        "/api/v1/auth/register",
        json={"email": "DUPLICATE@example.com", "full_name": "Second", "password": VALID_PASSWORD},
    )
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json() == {"detail": "An account with this email already exists"}


def test_invalid_email_is_rejected_without_echoing_submitted_values(api_client):
    response = api_client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email-secret", "full_name": "Person", "password": VALID_PASSWORD},
    )
    assert response.status_code == 422
    assert "not-an-email-secret" not in response.text
    assert VALID_PASSWORD not in response.text


@pytest.mark.parametrize("password", ["Short1!", "alllowercasepassword", "NoDigitsOrSymbols"])
def test_weak_password_is_rejected_without_echoing_it(api_client, password):
    response = api_client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "full_name": "Person", "password": password},
    )
    assert response.status_code == 422
    assert password not in response.text


def test_registration_rejects_client_role_escalation(api_client):
    response = api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "attacker@example.com",
            "full_name": "Attacker",
            "password": VALID_PASSWORD,
            "role": "administrator",
        },
    )
    assert response.status_code == 422
    assert VALID_PASSWORD not in response.text


def test_login_returns_access_token_and_safe_user(api_client):
    registration = api_client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "full_name": "Login User", "password": VALID_PASSWORD},
    )
    assert registration.status_code == 201

    response = api_client.post(
        "/api/v1/auth/login", data={"username": "LOGIN@example.com", "password": VALID_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "login@example.com"
    assert "password_hash" not in response.text
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims["sub"] == registration.json()["id"]
    assert "exp" in claims
    profile = api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert profile.status_code == 200
    assert profile.json() == body["user"]


def test_wrong_password_and_unknown_account_share_generic_error(api_client):
    api_client.post(
        "/api/v1/auth/register",
        json={"email": "known@example.com", "full_name": "Known", "password": VALID_PASSWORD},
    )
    wrong = api_client.post(
        "/api/v1/auth/login",
        data={"username": "known@example.com", "password": "Wrong-Passphrase-2026!"},
    )
    unknown = api_client.post(
        "/api/v1/auth/login",
        data={"username": "unknown@example.com", "password": "Wrong-Passphrase-2026!"},
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}


def test_inactive_user_cannot_log_in_or_use_existing_token(api_client, db_session):
    user = _seed_user(db_session, active=False)
    login = api_client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": VALID_PASSWORD}
    )
    profile = api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {create_access_token(user.id)}"}
    )
    assert login.status_code == profile.status_code == 401
    assert login.json() == {"detail": "Invalid email or password"}
    assert profile.json() == {"detail": "Could not validate credentials"}


def test_current_user_rejects_missing_and_invalid_tokens(api_client):
    assert api_client.get("/api/v1/auth/me").status_code == 401
    invalid = api_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer invalid.signature.value"}
    )
    assert invalid.status_code == 401
    assert invalid.json() == {"detail": "Could not validate credentials"}
    assert "invalid.signature.value" not in invalid.text


def test_tampered_jwt_signature_is_rejected(api_client, db_session):
    user = _seed_user(db_session)
    token = create_access_token(user.id)
    header, payload, signature = token.split(".")
    changed_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    response = api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {header}.{payload}.{changed_signature}"},
    )
    assert response.status_code == 401


def test_expired_token_is_rejected(api_client, db_session):
    from app.core.config import get_settings

    user = _seed_user(db_session)
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": str(user.id), "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)},
        get_settings().secret_key,
        algorithm="HS256",
    )
    response = api_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("role", "dependency"),
    [
        ("citizen", require_citizen),
        ("engineer", require_engineer),
        ("officer", require_officer),
        ("administrator", require_administrator),
    ],
)
def test_each_project_role_can_pass_its_role_dependency(db_session, role, dependency):
    user = _seed_user(db_session, role=role)
    protected = FastAPI()
    role_dependency = Depends(dependency)

    @protected.get("/protected")
    def protected_route(current: User = role_dependency):
        return {"role": current.role}

    from app.db.session import get_session

    def override_session():
        yield db_session

    protected.dependency_overrides[get_session] = override_session
    token = create_access_token(user.id)
    response = TestClient(protected).get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"role": role}


def test_role_dependency_denies_disallowed_users_and_supports_role_combinations(db_session):
    citizen = _seed_user(db_session, role="citizen")
    protected = FastAPI()
    administrator_dependency = Depends(require_administrator)
    staff_dependency = Depends(require_roles("engineer", "officer"))

    @protected.get("/admin")
    def admin_route(current: User = administrator_dependency):
        return {"id": str(current.id)}

    @protected.get("/staff")
    def staff_route(current: User = staff_dependency):
        return {"role": current.role}

    from app.db.session import get_session

    def override_session():
        yield db_session

    protected.dependency_overrides[get_session] = override_session
    client = TestClient(protected)
    token = create_access_token(citizen.id)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/admin", headers=headers).status_code == 403
    assert client.get("/staff", headers=headers).status_code == 403
    assert client.get("/admin").status_code == 401

    officer = _seed_user(db_session, role="officer")
    response = client.get(
        "/staff", headers={"Authorization": f"Bearer {create_access_token(officer.id)}"}
    )
    assert response.status_code == 200
    assert response.json() == {"role": "officer"}


def test_openapi_and_swagger_document_authentication(api_client):
    docs = api_client.get("/docs")
    specification = api_client.get("/openapi.json")
    assert docs.status_code == specification.status_code == 200
    openapi = specification.json()
    assert "/api/v1/auth/register" in openapi["paths"]
    assert "/api/v1/auth/login" in openapi["paths"]
    assert "/api/v1/auth/me" in openapi["paths"]
    assert "/api/v1/water-bodies" in openapi["paths"]
    assert "JWT Bearer" in openapi["components"]["securitySchemes"]
    assert openapi["paths"]["/api/v1/auth/me"]["get"]["security"]


def test_login_email_is_parameterized_and_cannot_inject_sql(api_client):
    response = api_client.post(
        "/api/v1/auth/login",
        data={"username": "nobody@example.com' OR 1=1 --", "password": VALID_PASSWORD},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}
