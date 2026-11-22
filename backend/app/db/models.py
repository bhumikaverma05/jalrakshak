"""Normalized MVP data models using PostgreSQL and PostGIS."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('citizen','engineer','officer','administrator')", name="role_valid"
        ),
        Index("ix_users_role_active", "role", "is_active"),
        Index("uq_users_email_normalized", text("lower(email)"), unique=True),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="citizen")
    phone: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WaterBody(TimestampMixin, Base):
    __tablename__ = "water_bodies"
    __table_args__ = (
        CheckConstraint(
            "data_status IN ('preliminary','verified','rejected')", name="data_status_valid"
        ),
        CheckConstraint(
            "ST_X(location) BETWEEN -180 AND 180 AND ST_Y(location) BETWEEN -90 AND 90",
            name="location_wgs84_range",
        ),
        CheckConstraint("boundary IS NULL OR ST_IsValid(boundary)", name="boundary_valid"),
        CheckConstraint("area_sq_km IS NULL OR area_sq_km >= 0", name="area_nonnegative"),
        Index("ix_water_bodies_location", "location", postgresql_using="gist"),
        Index("ix_water_bodies_boundary", "boundary", postgresql_using="gist"),
        Index("ix_water_bodies_type_status", "water_body_type", "data_status"),
        Index("ix_water_bodies_district_state", "district", "state"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    water_body_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    water_body_type: Mapped[str] = mapped_column(String(40), nullable=False)
    village: Mapped[str | None] = mapped_column(String(160))
    district: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=False
    )
    boundary: Mapped[Any | None] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False)
    )
    area_sq_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    responsible_authority: Mapped[str | None] = mapped_column(String(200))
    data_status: Mapped[str] = mapped_column(String(20), nullable=False, default="preliminary")
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class PreliminaryAssessment(TimestampMixin, Base):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("garbage_score BETWEEN 0 AND 4", name="garbage_score_range"),
        CheckConstraint("algal_stress_score BETWEEN 0 AND 4", name="algal_score_range"),
        CheckConstraint("sewage_score BETWEEN 0 AND 4", name="sewage_score_range"),
        CheckConstraint("encroachment_score BETWEEN 0 AND 4", name="encroachment_score_range"),
        CheckConstraint("shrinkage_score BETWEEN 0 AND 4", name="shrinkage_score_range"),
        CheckConstraint("total_degradation_score BETWEEN 0 AND 20", name="total_score_range"),
        CheckConstraint(
            "total_degradation_score = garbage_score + algal_stress_score + sewage_score + encroachment_score + shrinkage_score",
            name="total_score_matches_components",
        ),
        CheckConstraint(
            "verification_status IN ('preliminary','submitted','verified','rejected')",
            name="verification_status_valid",
        ),
        Index("ix_assessments_water_date", "water_body_id", "assessment_date"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    water_body_id: Mapped[UUID] = mapped_column(
        ForeignKey("water_bodies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assessed_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assessment_date: Mapped[date] = mapped_column(Date, nullable=False)
    garbage_score: Mapped[int] = mapped_column(nullable=False)
    algal_stress_score: Mapped[int] = mapped_column(nullable=False)
    sewage_score: Mapped[int] = mapped_column(nullable=False)
    encroachment_score: Mapped[int] = mapped_column(nullable=False)
    shrinkage_score: Mapped[int] = mapped_column(nullable=False)
    total_degradation_score: Mapped[int] = mapped_column(nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="preliminary"
    )
    remarks: Mapped[str | None] = mapped_column(Text)


class FieldObservation(TimestampMixin, Base):
    __tablename__ = "field_observations"
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('preliminary','submitted','verified','rejected')",
            name="verification_status_valid",
        ),
        CheckConstraint(
            "observation_location IS NULL OR (ST_X(observation_location) BETWEEN -180 AND 180 AND ST_Y(observation_location) BETWEEN -90 AND 90)",
            name="observation_location_wgs84_range",
        ),
        CheckConstraint(
            "gps_accuracy_m IS NULL OR gps_accuracy_m >= 0", name="gps_accuracy_nonnegative"
        ),
        Index("ix_field_observations_water_observed", "water_body_id", "observed_at"),
        Index("ix_field_observations_location", "observation_location", postgresql_using="gist"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    water_body_id: Mapped[UUID] = mapped_column(
        ForeignKey("water_bodies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    observer_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observation_location: Mapped[Any | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )
    gps_accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(9, 2))
    observed_condition: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="preliminary"
    )


class CitizenReport(TimestampMixin, Base):
    __tablename__ = "citizen_reports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('submitted','under_review','assigned','resolved','rejected')",
            name="status_valid",
        ),
        CheckConstraint(
            "ST_X(reported_location) BETWEEN -180 AND 180 AND ST_Y(reported_location) BETWEEN -90 AND 90",
            name="reported_location_wgs84_range",
        ),
        CheckConstraint(
            "gps_accuracy_m IS NULL OR gps_accuracy_m >= 0", name="gps_accuracy_nonnegative"
        ),
        Index("ix_citizen_reports_location", "reported_location", postgresql_using="gist"),
        Index("ix_citizen_reports_status_created", "status", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    water_body_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("water_bodies.id", ondelete="RESTRICT"), index=True
    )
    reporter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    assigned_to: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reported_location: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=False
    )
    gps_accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(9, 2))
    location_description: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="submitted")


class Evidence(TimestampMixin, Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(
            "field_observation_id IS NOT NULL OR citizen_report_id IS NOT NULL",
            name="parent_required",
        ),
        CheckConstraint("file_size_bytes >= 0", name="file_size_nonnegative"),
        CheckConstraint(
            "gps_location IS NULL OR (ST_X(gps_location) BETWEEN -180 AND 180 AND ST_Y(gps_location) BETWEEN -90 AND 90)",
            name="gps_location_wgs84_range",
        ),
        Index("ix_evidence_location", "gps_location", postgresql_using="gist"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    field_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("field_observations.id", ondelete="RESTRICT"), index=True
    )
    citizen_report_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("citizen_reports.id", ondelete="RESTRICT"), index=True
    )
    uploaded_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gps_location: Mapped[Any | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )
    metadata_validation_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending"
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WaterQualityReading(Base):
    __tablename__ = "water_quality_readings"
    __table_args__ = (
        CheckConstraint("ph IS NULL OR ph BETWEEN 0 AND 14", name="ph_range"),
        CheckConstraint("tds_mg_l IS NULL OR tds_mg_l >= 0", name="tds_nonnegative"),
        CheckConstraint(
            "turbidity_ntu IS NULL OR turbidity_ntu >= 0", name="turbidity_nonnegative"
        ),
        CheckConstraint(
            "temperature_c IS NULL OR temperature_c >= -273.15", name="temperature_valid"
        ),
        Index("ix_water_quality_water_reading", "water_body_id", "reading_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    water_body_id: Mapped[UUID] = mapped_column(
        ForeignKey("water_bodies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    recorded_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reading_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ph: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    tds_mg_l: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    turbidity_ntu: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    instrument: Mapped[str | None] = mapped_column(String(120))
    remarks: Mapped[str | None] = mapped_column(Text)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SatelliteObservation(Base):
    __tablename__ = "satellite_observations"
    __table_args__ = (
        UniqueConstraint("satellite", "scene_id", name="uq_satellite_scene"),
        CheckConstraint("cloud_percentage BETWEEN 0 AND 100", name="cloud_percentage_range"),
        CheckConstraint(
            "estimated_area_sq_km IS NULL OR estimated_area_sq_km >= 0", name="area_nonnegative"
        ),
        Index("ix_satellite_water_acquired", "water_body_id", "acquired_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    water_body_id: Mapped[UUID] = mapped_column(
        ForeignKey("water_bodies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    recorded_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    satellite: Mapped[str] = mapped_column(String(80), nullable=False)
    scene_id: Mapped[str] = mapped_column(String(160), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cloud_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    ndwi: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    mndwi: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    ndti: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    ndci: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    estimated_area_sq_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    image_storage_key: Mapped[str | None] = mapped_column(String(512))
    processing_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual_record"
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity_created", "entity_type", "entity_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
