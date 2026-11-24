"""Citizen-report API request and response contracts."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domains.evidence.schemas import EvidenceResponse


class ReportCategory(StrEnum):
    GARBAGE_DUMPING = "garbage_dumping"
    PLASTIC_POLLUTION = "plastic_pollution"
    UNUSUAL_COLOUR = "unusual_colour"
    FOUL_SMELL = "foul_smell"
    ENCROACHMENT = "encroachment"
    OTHER = "other"


class ReportStatus(StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    VERIFIED = "verified"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class GeoJSONPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float] = Field(description="Longitude, latitude in WGS84 order")

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, value: tuple[float, float]) -> tuple[float, float]:
        longitude, latitude = value
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            raise ValueError("Coordinates must be longitude/latitude in WGS84 ranges")
        return value


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: ReportCategory
    description: str = Field(min_length=1, max_length=5000)
    reported_location: GeoJSONPoint
    gps_accuracy_m: Decimal | None = Field(default=None, ge=0, le=1_000_000)
    location_description: str | None = Field(default=None, max_length=300)
    water_body_id: UUID | None = None

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Description cannot be blank")
        return value

    @field_validator("location_description")
    @classmethod
    def clean_location_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ReportUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReportStatus | None = None
    assigned_to: UUID | None = None
    water_body_id: UUID | None = None
    review_note: str | None = Field(default=None, max_length=2000)

    @field_validator("review_note")
    @classmethod
    def clean_review_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def require_an_update(self) -> "ReportUpdate":
        if not ({"status", "assigned_to", "water_body_id"} & self.model_fields_set):
            raise ValueError("Provide a status, assignment, or water-body update")
        if self.status is None and "status" in self.model_fields_set:
            raise ValueError("Status cannot be null")
        return self


class CitizenReportResponse(BaseModel):
    id: UUID
    water_body_id: UUID | None
    reporter_id: UUID | None
    assigned_to: UUID | None
    category: ReportCategory
    description: str
    reported_location: dict[str, Any]
    gps_accuracy_m: Decimal | None
    location_description: str | None
    status: ReportStatus
    created_at: datetime
    updated_at: datetime
    evidence: list[EvidenceResponse] = Field(default_factory=list)


class CitizenReportPage(BaseModel):
    items: list[CitizenReportResponse]
    total: int
    page: int
    page_size: int


class AuditEntryResponse(BaseModel):
    id: UUID
    actor_id: UUID | None
    action: str
    changes: dict[str, Any]
    created_at: datetime
