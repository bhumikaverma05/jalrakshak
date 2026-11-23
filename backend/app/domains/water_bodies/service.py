"""Parameterized read services for water-body records."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import WaterBody
from app.domains.water_bodies.schemas import WaterBodyPage, WaterBodyResponse


def _response(row: Any) -> WaterBodyResponse:
    return WaterBodyResponse(
        id=row.id,
        water_body_code=row.water_body_code,
        name=row.name,
        water_body_type=row.water_body_type,
        village=row.village,
        district=row.district,
        state=row.state,
        description=row.description,
        area_sq_km=row.area_sq_km,
        responsible_authority=row.responsible_authority,
        data_status=row.data_status,
        location=json.loads(row.location_geojson) if row.location_geojson else None,
        boundary=json.loads(row.boundary_geojson) if row.boundary_geojson else None,
    )


def _spatial_select():
    return select(
        WaterBody.id,
        WaterBody.water_body_code,
        WaterBody.name,
        WaterBody.water_body_type,
        WaterBody.village,
        WaterBody.district,
        WaterBody.state,
        WaterBody.description,
        WaterBody.area_sq_km,
        WaterBody.responsible_authority,
        WaterBody.data_status,
        func.ST_AsGeoJSON(WaterBody.location).label("location_geojson"),
        func.ST_AsGeoJSON(WaterBody.boundary).label("boundary_geojson"),
    )


def list_water_bodies(session: Session, page: int, page_size: int) -> WaterBodyPage:
    """Return one stable, bounded page and total count in two SQL queries."""
    total = session.scalar(select(func.count()).select_from(WaterBody)) or 0
    rows = session.execute(
        _spatial_select()
        .order_by(WaterBody.name, WaterBody.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return WaterBodyPage(
        items=[_response(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_water_body(session: Session, water_body_id: UUID) -> WaterBodyResponse | None:
    """Load one record with GeoJSON in the same query; missing geometry stays null."""
    row = session.execute(_spatial_select().where(WaterBody.id == water_body_id)).one_or_none()
    return _response(row) if row else None
