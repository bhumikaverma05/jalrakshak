"""Water-body API response contracts."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WaterBodyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    water_body_code: str
    name: str
    water_body_type: str
    village: str | None
    district: str
    state: str
    description: str | None
    area_sq_km: Decimal | None
    responsible_authority: str | None
    data_status: str
    location: dict[str, Any] | None
    boundary: dict[str, Any] | None


class WaterBodyPage(BaseModel):
    items: list[WaterBodyResponse]
    total: int
    page: int
    page_size: int
