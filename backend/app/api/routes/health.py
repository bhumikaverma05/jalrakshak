"""Health endpoints that do not depend on database availability."""

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import check_database_connection

router = APIRouter(tags=["health"])


@router.get("/health", summary="API health check")
def api_health() -> dict[str, str]:
    """Report that the API process is responding."""
    return {"status": "ok", "service": get_settings().app_name}


@router.get("/health/database", summary="Database and PostGIS readiness")
def database_health() -> dict[str, str]:
    """Report safe database versions; never expose the connection string."""
    try:
        return {"status": "ok", **check_database_connection()}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
