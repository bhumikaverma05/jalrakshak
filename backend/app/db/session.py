"""Database engine and request-scoped session dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,
    connect_args={"connect_timeout": settings.database_connect_timeout},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """Yield a request-scoped transaction and always close the session."""
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
            session.info.pop("pending_evidence_files", None)
        except Exception:
            try:
                session.rollback()
            finally:
                # File writes are registered by the evidence service so a failed
                # request commit does not leave an orphaned upload behind.
                from app.domains.evidence.service import cleanup_pending_files

                cleanup_pending_files(session)
            raise


def check_database_connection() -> dict[str, str]:
    """Return safe database/PostGIS version data or raise the DB error."""
    with engine.connect() as connection:
        database = connection.execute(text("SELECT current_database()")).scalar_one()
        postgres_version = connection.execute(text("SHOW server_version")).scalar_one()
        postgis_version = connection.execute(text("SELECT PostGIS_Version()")).scalar_one()
    return {
        "database": database,
        "postgres_version": postgres_version,
        "postgis_version": postgis_version,
    }
