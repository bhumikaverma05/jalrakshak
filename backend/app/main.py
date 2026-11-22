"""FastAPI application factory and top-level health endpoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="JalRakshak API with the Milestone 3 PostgreSQL/PostGIS persistence foundation.",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Accept", "Authorization", "Content-Type"],
    )
    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.get("/healthz", tags=["health"], summary="Process liveness")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
