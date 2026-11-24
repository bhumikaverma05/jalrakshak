"""Pure processing tests using synthetic arrays; no database or satellite data."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import numpy as np
import pytest
from rasterio.crs import CRS
from rasterio.transform import from_origin

from app.db.models import SatelliteObservation
from app.domains.satellite.processing import (
    ProcessingSettings,
    RasterBand,
    SatelliteProcessingError,
    SatelliteProcessingResult,
    Sentinel2RasterInputs,
    compare_historical_area,
    local_utm_crs,
    process_sentinel2_bands,
)
from app.domains.satellite.service import (
    SatelliteObservationNotFoundError,
    SceneAlreadyRecordedError,
    WaterBodyNotEligibleError,
    get_observation,
    list_observations,
    store_processed_observation,
)
from app.main import app

_BOUNDARY = {
    "type": "Polygon",
    "coordinates": [
        [
            [-0.0005, -0.0005],
            [0.0005, -0.0005],
            [0.0005, 0.0005],
            [-0.0005, 0.0005],
            [-0.0005, -0.0005],
        ]
    ],
}


def _synthetic_inputs() -> Sentinel2RasterInputs:
    crs = CRS.from_epsg(3857)
    green_10m = np.full((12, 12), 0.6, dtype=np.float32)
    swir_20m = np.full((6, 6), 0.2, dtype=np.float32)
    scl_20m = np.full((6, 6), 4, dtype=np.uint8)
    # A dry pixel, cloud, shadow, no-data, and snow exercise masks and thresholding.
    swir_20m[0, 0] = 0.8
    scl_20m[0, 1] = 7
    scl_20m[1, 1] = 9
    scl_20m[2, 2] = 3
    scl_20m[3, 3] = 0
    scl_20m[4, 4] = 11
    return Sentinel2RasterInputs(
        b03_green=RasterBand(green_10m, from_origin(-60, 60, 10, 10), crs),
        b11_swir1=RasterBand(swir_20m, from_origin(-60, 60, 20, 20), crs),
        scl=RasterBand(scl_20m, from_origin(-60, 60, 20, 20), crs, nodata=0),
    )


def test_mndwi_alignment_cloud_mask_threshold_and_square_metre_area():
    result = process_sentinel2_bands(
        _synthetic_inputs(),
        _BOUNDARY,
        settings=ProcessingSettings(mndwi_water_threshold=0.1, analysis_pixel_size_m=20),
        analysis_crs="EPSG:3857",
    )

    assert result.analysis_crs == "EPSG:3857"
    assert result.valid_pixel_count > result.water_pixel_count > 0
    assert result.cloud_percentage > 0
    assert result.water_area_sq_m == result.water_pixel_count * 400
    assert np.isnan(result.mndwi[0, 1])
    assert np.isnan(result.mndwi[1, 1])
    assert np.isnan(result.mndwi[2, 2])
    assert np.isnan(result.mndwi[3, 3])
    assert np.isnan(result.mndwi[4, 4])
    assert result.water_mask[0, 0] == np.False_


def test_water_threshold_is_configurable():
    inputs = _synthetic_inputs()
    permissive = process_sentinel2_bands(
        inputs,
        _BOUNDARY,
        settings=ProcessingSettings(mndwi_water_threshold=-0.9),
        analysis_crs="EPSG:3857",
    )
    strict = process_sentinel2_bands(
        inputs,
        _BOUNDARY,
        settings=ProcessingSettings(mndwi_water_threshold=0.2),
        analysis_crs="EPSG:3857",
    )
    assert strict.water_pixel_count < permissive.water_pixel_count


def test_scene_classification_is_aligned_with_nearest_neighbor():
    result = process_sentinel2_bands(_synthetic_inputs(), _BOUNDARY, analysis_crs="EPSG:3857")
    assert result.valid_mask.shape == result.water_mask.shape == result.mndwi.shape
    assert result.analysis_pixel_size_m == 20


def test_local_utm_crs_uses_boundary_location():
    bhopal_boundary = {
        "type": "Polygon",
        "coordinates": [[[77.3, 23.1], [77.5, 23.1], [77.5, 23.3], [77.3, 23.3], [77.3, 23.1]]],
    }
    assert local_utm_crs(bhopal_boundary).to_epsg() == 32643


def test_invalid_boundary_and_crs_are_rejected():
    with pytest.raises(SatelliteProcessingError, match="boundary is required"):
        process_sentinel2_bands(_synthetic_inputs(), {}, analysis_crs="EPSG:3857")
    with pytest.raises(SatelliteProcessingError, match="projected in metres"):
        process_sentinel2_bands(_synthetic_inputs(), _BOUNDARY, analysis_crs="EPSG:4326")


def test_extremely_large_boundary_is_rejected_before_raster_allocation():
    large_boundary = {
        "type": "Polygon",
        "coordinates": [[[-0.6, -0.6], [0.6, -0.6], [0.6, 0.6], [-0.6, 0.6], [-0.6, -0.6]]],
    }
    with pytest.raises(SatelliteProcessingError, match="processing limit"):
        process_sentinel2_bands(_synthetic_inputs(), large_boundary)


def test_historical_area_comparison_handles_missing_and_zero_baseline():
    assert compare_historical_area(500, None) == {
        "previous_area_sq_m": None,
        "delta_area_sq_m": None,
        "change_percent": None,
    }
    assert compare_historical_area(500, 0) == {
        "previous_area_sq_m": 0,
        "delta_area_sq_m": 500,
        "change_percent": None,
    }
    assert compare_historical_area(750, 500) == {
        "previous_area_sq_m": 500,
        "delta_area_sq_m": 250,
        "change_percent": 50,
    }
    with pytest.raises(ValueError, match="cannot be negative"):
        compare_historical_area(0, -1)


def _fixed_result(area_sq_m: float = 12_345) -> SatelliteProcessingResult:
    return SatelliteProcessingResult(
        mndwi=np.array([[0.4]], dtype=np.float32),
        valid_mask=np.array([[True]]),
        water_mask=np.array([[True]]),
        mean_mndwi=0.4,
        cloud_percentage=2.5,
        water_pixel_count=1,
        valid_pixel_count=1,
        water_area_sq_m=area_sq_m,
        analysis_crs="EPSG:32643",
        analysis_pixel_size_m=20,
        mndwi_water_threshold=0.0,
    )


def _mock_session(*, boundary_status="verified", boundary=_BOUNDARY, scalar_results=None):
    from unittest.mock import Mock

    session = Mock()
    session.execute.return_value.one_or_none.return_value = (
        boundary_status,
        json.dumps(boundary) if boundary else None,
    )
    session.scalar.side_effect = scalar_results or [None, None]
    session.scalars.return_value.all.return_value = []
    return session


@pytest.mark.parametrize(
    ("boundary_status", "boundary"),
    [("preliminary", _BOUNDARY), ("rejected", _BOUNDARY), ("verified", None)],
)
def test_storage_refuses_unverified_or_missing_boundaries(monkeypatch, boundary_status, boundary):
    from app.domains.satellite import service

    session = _mock_session(boundary_status=boundary_status, boundary=boundary)
    monkeypatch.setattr(
        service,
        "process_sentinel2_bands",
        lambda *args, **kwargs: pytest.fail("ineligible boundary must not be processed"),
    )
    with pytest.raises(WaterBodyNotEligibleError):
        store_processed_observation(
            session,
            water_body_id=uuid4(),
            scene_id="synthetic-scene",
            acquired_at=datetime(2026, 1, 1, tzinfo=UTC),
            scene_cloud_percentage=0,
            inputs=_synthetic_inputs(),
            settings=ProcessingSettings(),
        )
    session.add.assert_not_called()


def test_storage_converts_square_metres_and_keeps_provenance(monkeypatch):
    from app.domains.satellite import service

    water_body_id = uuid4()
    session = _mock_session()
    monkeypatch.setattr(service, "process_sentinel2_bands", lambda *args, **kwargs: _fixed_result())

    observation = store_processed_observation(
        session,
        water_body_id=water_body_id,
        scene_id="synthetic-scene",
        acquired_at=datetime(2026, 1, 2, tzinfo=UTC),
        scene_cloud_percentage=1,
        inputs=_synthetic_inputs(),
        settings=ProcessingSettings(mndwi_water_threshold=0.15, analysis_pixel_size_m=20),
    )

    assert observation.estimated_area_sq_km == Decimal("0.012345")
    assert observation.cloud_percentage == Decimal(1)
    assert observation.provenance["area"]["water_area_sq_m"] == 12_345
    assert observation.provenance["mndwi"]["water_threshold"] == 0.15
    assert observation.provenance["area"]["analysis_crs"] == "EPSG:32643"
    assert observation.provenance["historical_comparison"]["delta_area_sq_m"] is None
    assert session.scalar.call_count == 1
    assert session.scalars.call_count == 1


def test_storage_uses_exact_previous_square_metre_provenance(monkeypatch):
    from app.domains.satellite import service

    water_body_id = uuid4()
    previous = SatelliteObservation(
        id=uuid4(),
        water_body_id=water_body_id,
        satellite="Sentinel-2",
        scene_id="old-scene",
        acquired_at=datetime(2026, 1, 1, tzinfo=UTC),
        cloud_percentage=Decimal(0),
        estimated_area_sq_km=Decimal("0.0100"),
        processing_status="processed",
        provenance={
            "processing_version": 1,
            "mndwi": {"water_threshold": 0.0},
            "area": {
                "water_area_sq_m": 10_001,
                "pixel_size_m": 20,
                "analysis_crs": "EPSG:32643",
            },
        },
    )
    incompatible = SatelliteObservation(
        id=uuid4(),
        water_body_id=water_body_id,
        satellite="Sentinel-2",
        scene_id="incompatible-scene",
        acquired_at=datetime(2026, 1, 1, 12, tzinfo=UTC),
        cloud_percentage=Decimal(0),
        estimated_area_sq_km=Decimal("0.0200"),
        processing_status="processed",
        provenance={
            "processing_version": 1,
            "mndwi": {"water_threshold": 0.5},
            "area": {
                "water_area_sq_m": 20_000,
                "pixel_size_m": 20,
                "analysis_crs": "EPSG:32643",
            },
        },
    )
    session = _mock_session(scalar_results=[None])
    session.scalars.return_value.all.return_value = [incompatible, previous]
    monkeypatch.setattr(service, "process_sentinel2_bands", lambda *args, **kwargs: _fixed_result())

    observation = store_processed_observation(
        session,
        water_body_id=water_body_id,
        scene_id="new-scene",
        acquired_at=datetime(2026, 1, 2, tzinfo=UTC),
        scene_cloud_percentage=1,
        inputs=_synthetic_inputs(),
        settings=ProcessingSettings(),
    )

    comparison = observation.provenance["historical_comparison"]
    assert comparison["previous_observation_id"] == str(previous.id)
    assert comparison["previous_area_sq_m"] == 10_001
    assert comparison["delta_area_sq_m"] == 2_344


def test_existing_global_scene_constraint_is_reported_before_processing(monkeypatch):
    from app.domains.satellite import service

    session = _mock_session(scalar_results=[uuid4()])
    monkeypatch.setattr(
        service,
        "process_sentinel2_bands",
        lambda *args, **kwargs: pytest.fail("duplicate source scene must not be processed"),
    )
    with pytest.raises(SceneAlreadyRecordedError, match="global unique key"):
        store_processed_observation(
            session,
            water_body_id=uuid4(),
            scene_id="already-used-scene",
            acquired_at=datetime(2026, 1, 2, tzinfo=UTC),
            scene_cloud_percentage=1,
            inputs=_synthetic_inputs(),
            settings=ProcessingSettings(),
        )
    session.execute.assert_not_called()
    session.add.assert_not_called()


def test_satellite_read_apis_are_registered():
    paths = app.openapi()["paths"]
    assert "/api/v1/satellite/water-bodies/{water_body_id}/observations" in paths
    assert "/api/v1/satellite/observations/{observation_id}" in paths


def test_observation_history_service_returns_safe_ordered_response():
    from unittest.mock import Mock

    water_body_id = uuid4()
    observation = SatelliteObservation(
        id=uuid4(),
        water_body_id=water_body_id,
        satellite="Sentinel-2",
        scene_id="synthetic-scene",
        acquired_at=datetime(2026, 1, 1),
        cloud_percentage=Decimal("2.5"),
        mndwi=Decimal("0.4"),
        estimated_area_sq_km=Decimal("0.0123"),
        image_storage_key="private/key.tif",
        processing_status="processed",
        provenance={"area": {"water_area_sq_m": 12_345}},
    )
    session = Mock()
    session.scalar.return_value = 1
    session.scalars.return_value.all.return_value = [observation]

    page = list_observations(session, water_body_id=water_body_id, page=1, page_size=20)

    assert page.total == 1
    assert page.items[0].scene_id == "synthetic-scene"
    assert page.items[0].provenance["area"]["water_area_sq_m"] == 12_345
    assert "image_storage_key" not in page.items[0].model_dump()


def test_observation_detail_returns_not_found_without_database():
    from unittest.mock import Mock

    session = Mock()
    session.get.return_value = None
    with pytest.raises(SatelliteObservationNotFoundError):
        get_observation(session, observation_id=uuid4())


def test_satellite_api_requires_authentication_and_staff_role():
    from types import SimpleNamespace
    from unittest.mock import Mock

    from fastapi.testclient import TestClient

    from app.db.session import get_session
    from app.domains.auth.dependencies import get_current_user

    water_body_id = uuid4()
    path = f"/api/v1/satellite/water-bodies/{water_body_id}/observations"
    session = Mock()
    session.get.return_value = None

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            unauthenticated = client.get(path)
            assert unauthenticated.status_code == 401

            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="citizen")
            forbidden = client.get(path)
            assert forbidden.status_code == 403

            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="engineer")
            permitted = client.get(path)
            assert permitted.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_session, None)
