"""Safe fixtures for explicitly named PostgreSQL test databases."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from alembic import command

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-never-use-outside-tests-0123456789")


def validate_test_database_url(url: str) -> None:
    """Allow integration tests only on the named database through host port 5433."""
    parsed = make_url(url)
    if (
        parsed.database != "jalrakshak_test"
        or parsed.host not in {"localhost", "127.0.0.1"}
        or parsed.port != 5433
    ):
        raise ValueError("Integration tests require jalrakshak_test on localhost port 5433")


@pytest.fixture(scope="session")
def postgres_engine() -> Iterator[Engine]:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set TEST_DATABASE_URL to a disposable PostgreSQL/PostGIS database ending in _test"
        )
    try:
        validate_test_database_url(url)
    except ValueError as exc:
        pytest.fail(f"Refusing database integration tests: {exc}")
    os.environ["DATABASE_URL"] = url
    from app.core.config import get_settings

    get_settings.cache_clear()
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()
        get_settings.cache_clear()


@pytest.fixture
def db_session(postgres_engine: Engine) -> Iterator[Session]:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
