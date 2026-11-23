"""Read-only water-body registry endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.domains.water_bodies.schemas import WaterBodyPage, WaterBodyResponse
from app.domains.water_bodies.service import get_water_body, list_water_bodies

router = APIRouter()


@router.get("", response_model=WaterBodyPage, summary="List water bodies")
def read_water_bodies(
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> WaterBodyPage:
    try:
        return list_water_bodies(session, page, page_size)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Water-body service is unavailable") from None


@router.get("/{water_body_id}", response_model=WaterBodyResponse, summary="Get water-body details")
def read_water_body(
    water_body_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> WaterBodyResponse:
    try:
        water_body = get_water_body(session, water_body_id)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Water-body service is unavailable") from None
    if water_body is None:
        raise HTTPException(status_code=404, detail="Water body not found")
    return water_body
