"""Versioned API router composition."""

from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.reports import router as reports_router
from app.api.routes.water_bodies import router as water_bodies_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router, prefix="/auth", tags=["authentication"])
api_router.include_router(reports_router, prefix="/reports", tags=["citizen reports"])
api_router.include_router(water_bodies_router, prefix="/water-bodies", tags=["water bodies"])
