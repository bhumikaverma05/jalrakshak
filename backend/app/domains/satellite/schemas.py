"""Safe API response contracts for stored satellite observations."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SatelliteObservationResponse(BaseModel):
    id: UUID
    water_body_id: UUID
    satellite: str
    scene_id: str
    acquired_at: datetime
    cloud_percentage: Decimal
    mndwi: Decimal | None
    estimated_area_sq_km: Decimal | None
    processing_status: str
    provenance: dict[str, Any]


class SatelliteObservationPage(BaseModel):
    items: list[SatelliteObservationResponse]
    total: int
    page: int
    page_size: int
