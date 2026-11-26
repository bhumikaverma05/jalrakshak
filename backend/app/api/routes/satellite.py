"""Read-only satellite observation and historical comparison APIs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import User, WaterBody
from app.db.session import get_session
from app.domains.auth.dependencies import require_roles
from app.domains.satellite.schemas import SatelliteObservationPage, SatelliteObservationResponse
from app.domains.satellite.service import (
    SatelliteObservationNotFoundError,
    get_observation,
    list_observations,
)

router = APIRouter()
SatelliteReader = Annotated[User, Depends(require_roles("officer", "engineer", "administrator"))]


@router.get(
    "/water-bodies/{water_body_id}/observations",
    response_model=SatelliteObservationPage,
    summary="List satellite observations for a water body",
)
def read_observations(
    water_body_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    actor: SatelliteReader,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SatelliteObservationPage:
    try:
        if session.get(WaterBody, water_body_id) is None:
            raise HTTPException(status_code=404, detail="Water body not found")
        return list_observations(
            session, water_body_id=water_body_id, page=page, page_size=page_size
        )
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Satellite service is unavailable") from None


@router.get(
    "/observations/{observation_id}",
    response_model=SatelliteObservationResponse,
    summary="Get a satellite observation",
)
def read_observation(
    observation_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    actor: SatelliteReader,
) -> SatelliteObservationResponse:
    try:
        return get_observation(session, observation_id=observation_id)
    except SatelliteObservationNotFoundError:
        raise HTTPException(status_code=404, detail="Satellite observation not found") from None
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Satellite service is unavailable") from None
