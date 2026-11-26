"""Persistence orchestration for verified-boundary satellite observations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import SatelliteObservation, WaterBody
from app.domains.satellite.processing import (
    ProcessingSettings,
    Sentinel2RasterInputs,
    compare_historical_area,
    process_sentinel2_bands,
)
from app.domains.satellite.schemas import (
    SatelliteObservationPage,
    SatelliteObservationResponse,
)


class WaterBodyNotEligibleError(ValueError):
    """Raised when no verified, non-empty boundary is available for processing."""


class SceneAlreadyRecordedError(ValueError):
    """Raised for a Sentinel-2 scene ID already used by the global unique key."""


class SatelliteObservationNotFoundError(LookupError):
    """Raised when the requested observation does not exist."""


def _verified_boundary(session: Session, water_body_id: UUID) -> Mapping[str, Any]:
    row = session.execute(
        select(WaterBody.data_status, func.ST_AsGeoJSON(WaterBody.boundary)).where(
            WaterBody.id == water_body_id
        )
    ).one_or_none()
    if row is None:
        raise WaterBodyNotEligibleError("Water body not found")
    status, boundary_json = row
    if status != "verified" or not boundary_json:
        raise WaterBodyNotEligibleError("A verified water-body boundary is required")
    try:
        boundary = json.loads(boundary_json)
    except (TypeError, json.JSONDecodeError):
        raise WaterBodyNotEligibleError("Water-body boundary is invalid") from None
    if boundary.get("type") not in {"Polygon", "MultiPolygon"}:
        raise WaterBodyNotEligibleError("A Polygon or MultiPolygon boundary is required")
    return boundary


def store_processed_observation(
    session: Session,
    *,
    water_body_id: UUID,
    scene_id: str,
    acquired_at: datetime,
    scene_cloud_percentage: float,
    inputs: Sentinel2RasterInputs,
    recorded_by: UUID | None = None,
    settings: ProcessingSettings | None = None,
    image_storage_key: str | None = None,
) -> SatelliteObservation:
    """Process a supplied scene and stage its observation in the caller's transaction.

    The caller owns transaction commit/rollback. Only verified water bodies with
    a stored boundary can be processed. The kilometre field remains in km²;
    square metres and all calculation parameters are retained in provenance.
    """
    if not 0 <= scene_cloud_percentage <= 100:
        raise ValueError("Scene cloud percentage must be between 0 and 100")
    if acquired_at.tzinfo is None or acquired_at.utcoffset() is None:
        raise ValueError("Scene acquisition timestamp must include a timezone")
    if (
        session.scalar(
            select(SatelliteObservation.id).where(
                SatelliteObservation.satellite == "Sentinel-2",
                SatelliteObservation.scene_id == scene_id,
            )
        )
        is not None
    ):
        raise SceneAlreadyRecordedError(
            "The existing global unique key already records this satellite scene"
        )
    boundary = _verified_boundary(session, water_body_id)
    config = settings or ProcessingSettings(
        mndwi_water_threshold=get_settings().satellite_mndwi_water_threshold,
        analysis_pixel_size_m=get_settings().satellite_analysis_pixel_size_m,
    )
    result = process_sentinel2_bands(inputs, boundary, settings=config)

    previous_candidates = session.scalars(
        select(SatelliteObservation)
        .where(
            SatelliteObservation.water_body_id == water_body_id,
            SatelliteObservation.satellite == "Sentinel-2",
            SatelliteObservation.processing_status == "processed",
            SatelliteObservation.estimated_area_sq_km.is_not(None),
            SatelliteObservation.acquired_at < acquired_at,
        )
        .order_by(SatelliteObservation.acquired_at.desc(), SatelliteObservation.id)
    ).all()
    previous = next(
        (
            candidate
            for candidate in previous_candidates
            if _has_compatible_processing(candidate, config, result.analysis_crs)
        ),
        None,
    )
    previous_area_sq_m = None
    if previous is not None:
        previous_area_sq_m = (previous.provenance or {}).get("area", {}).get("water_area_sq_m")
        if previous_area_sq_m is None:
            # Older processed rows may lack square-metre provenance; retain a
            # documented fallback to the model's square-kilometre measurement.
            previous_area_sq_m = float(previous.estimated_area_sq_km) * 1_000_000
        previous_area_sq_m = float(previous_area_sq_m)
    historical = compare_historical_area(result.water_area_sq_m, previous_area_sq_m)
    provenance: dict[str, Any] = {
        "provider": "sentinel-2-l2a",
        "processing_version": 1,
        "mndwi": {
            "formula": "(B03 - B11) / (B03 + B11)",
            "green_band": "B03",
            "swir1_band": "B11",
            "summary_statistic": "mean of valid in-boundary pixels",
            "water_threshold": config.mndwi_water_threshold,
        },
        "cloud_mask": {
            "classification_band": "SCL",
            "excluded_classes": [0, 1, 3, 7, 8, 9, 10, 11],
            "cloud_percentage_classes": [3, 7, 8, 9, 10],
            "scene_cloud_percentage": scene_cloud_percentage,
            "boundary_cloud_percentage": result.cloud_percentage,
        },
        "area": {
            "water_area_sq_m": result.water_area_sq_m,
            "stored_area_unit": "square_kilometres",
            "pixel_size_m": result.analysis_pixel_size_m,
            "analysis_crs": result.analysis_crs,
            "water_pixel_count": result.water_pixel_count,
            "valid_pixel_count": result.valid_pixel_count,
        },
        "historical_comparison": {
            "previous_observation_id": str(previous.id) if previous is not None else None,
            **historical,
        },
    }
    observation = SatelliteObservation(
        water_body_id=water_body_id,
        recorded_by=recorded_by,
        satellite="Sentinel-2",
        scene_id=scene_id,
        acquired_at=acquired_at,
        cloud_percentage=Decimal(str(scene_cloud_percentage)),
        mndwi=Decimal(str(result.mean_mndwi)),
        estimated_area_sq_km=Decimal(str(result.water_area_sq_m / 1_000_000)),
        image_storage_key=image_storage_key,
        processing_status="processed",
        provenance=provenance,
    )
    session.add(observation)
    session.flush()
    return observation


def _has_compatible_processing(
    observation: SatelliteObservation, settings: ProcessingSettings, analysis_crs: str
) -> bool:
    provenance = observation.provenance
    if not isinstance(provenance, dict) or provenance.get("processing_version") != 1:
        return False
    mndwi = provenance.get("mndwi")
    area = provenance.get("area")
    return (
        isinstance(mndwi, dict)
        and isinstance(area, dict)
        and mndwi.get("water_threshold") == settings.mndwi_water_threshold
        and area.get("pixel_size_m") == settings.analysis_pixel_size_m
        and area.get("analysis_crs") == analysis_crs
    )


def _observation_response(row: SatelliteObservation) -> SatelliteObservationResponse:
    return SatelliteObservationResponse(
        id=row.id,
        water_body_id=row.water_body_id,
        satellite=row.satellite,
        scene_id=row.scene_id,
        acquired_at=row.acquired_at,
        cloud_percentage=row.cloud_percentage,
        mndwi=row.mndwi,
        estimated_area_sq_km=row.estimated_area_sq_km,
        processing_status=row.processing_status,
        provenance=row.provenance or {},
    )


def list_observations(
    session: Session, *, water_body_id: UUID, page: int, page_size: int
) -> SatelliteObservationPage:
    """Return a stable page of observation history for an existing water body."""
    total = (
        session.scalar(
            select(func.count())
            .select_from(SatelliteObservation)
            .where(SatelliteObservation.water_body_id == water_body_id)
        )
        or 0
    )
    rows = session.scalars(
        select(SatelliteObservation)
        .where(SatelliteObservation.water_body_id == water_body_id)
        .order_by(SatelliteObservation.acquired_at.desc(), SatelliteObservation.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return SatelliteObservationPage(
        items=[_observation_response(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_observation(session: Session, *, observation_id: UUID) -> SatelliteObservationResponse:
    """Return one stored observation without exposing its private storage key."""
    observation = session.get(SatelliteObservation, observation_id)
    if observation is None:
        raise SatelliteObservationNotFoundError
    return _observation_response(observation)
