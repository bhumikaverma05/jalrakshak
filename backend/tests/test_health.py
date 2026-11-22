import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import health
from app.core.config import Settings
from app.main import app

client = TestClient(app)


def test_process_health() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_versioned_api_health() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "JalRakshak API"}


def test_cors_allows_configured_frontend() -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_settings_load_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "JalRakshak Test API")
    monkeypatch.setenv(
        "CORS_ORIGINS",
        '["http://localhost:5173", "http://127.0.0.1:5173"]',
    )

    settings = Settings(_env_file=None)

    assert settings.app_name == "JalRakshak Test API"
    assert settings.cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_database_health_response_is_safe(monkeypatch) -> None:
    monkeypatch.setattr(
        health,
        "check_database_connection",
        lambda: {"database": "jalrakshak_test", "postgres_version": "19", "postgis_version": "3.4"},
    )

    response = client.get("/api/v1/health/database")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "password" not in response.text.lower()


def test_database_health_hides_connection_errors(monkeypatch) -> None:
    def fail() -> dict[str, str]:
        raise SQLAlchemyError("postgresql+psycopg://user:secret@host/database")

    monkeypatch.setattr(health, "check_database_connection", fail)
    response = client.get("/api/v1/health/database")

    assert response.status_code == 503
    assert "secret" not in response.text


def test_database_url_rejects_non_postgresql_schemes() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite:///not-supported.db")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="postgresql+psycopg://user:pw@/")
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+psycopg://user:change-me@localhost/jalrakshak_db",
        )
