"""Safe fixtures for explicitly named PostgreSQL test databases."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from alembic import command


@pytest.fixture(scope="session")
def postgres_engine() -> Iterator[Engine]:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set TEST_DATABASE_URL to a disposable PostgreSQL/PostGIS database ending in _test"
        )
    database = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not database.endswith("_test"):
        pytest.fail(
            "Refusing database integration tests: TEST_DATABASE_URL database name must end in _test"
        )
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
