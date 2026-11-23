"""Read-only registry API checks against the isolated PostGIS test database."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from geoalchemy2.elements import WKTElement
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes import water_bodies
from app.db.models import WaterBody
from app.main import app


@pytest.fixture
def registry_client(db_session: Session):
    from app.db.session import get_session

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)


def _water(session: Session, name: str, *, boundary: bool = True) -> WaterBody:
    record = WaterBody(
        water_body_code=f"API-{uuid4()}",
        name=name,
        water_body_type="pond",
        district="Test District",
        state="Test State",
        description="Synthetic API fixture",
        location=WKTElement("POINT(77.4 23.2)", srid=4326),
        boundary=(
            WKTElement(
                "MULTIPOLYGON(((77.3 23.1,77.5 23.1,77.5 23.3,77.3 23.3,77.3 23.1)))", srid=4326
            )
            if boundary
            else None
        ),
    )
    session.add(record)
    session.flush()
    return record


def test_list_returns_empty_page(registry_client):
    response = registry_client.get("/api/v1/water-bodies")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}


def test_list_paginates_and_returns_geojson(registry_client, db_session):
    _water(db_session, "Alpha")
    _water(db_session, "Beta", boundary=False)
    first = registry_client.get("/api/v1/water-bodies?page=1&page_size=1")
    second = registry_client.get("/api/v1/water-bodies?page=2&page_size=1")
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == 2
    assert first.json()["items"][0]["name"] == "Alpha"
    assert first.json()["items"][0]["location"] == {
        "type": "Point",
        "coordinates": [77.4, 23.2],
    }
    assert first.json()["items"][0]["boundary"]["type"] == "MultiPolygon"
    assert second.json()["items"][0]["boundary"] is None


@pytest.mark.parametrize("query", ["?page=0", "?page_size=0", "?page_size=101"])
def test_list_validates_pagination(query, registry_client):
    response = registry_client.get(f"/api/v1/water-bodies{query}")
    assert response.status_code == 422


def test_detail_returns_metadata_and_geojson(registry_client, db_session):
    record = _water(db_session, "Detail Pond")
    response = registry_client.get(f"/api/v1/water-bodies/{record.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Detail Pond"
    assert body["location"]["type"] == "Point"
    assert body["boundary"]["type"] == "MultiPolygon"


def test_detail_returns_null_when_boundary_is_unavailable(registry_client, db_session):
    record = _water(db_session, "No Boundary", boundary=False)
    response = registry_client.get(f"/api/v1/water-bodies/{record.id}")
    assert response.status_code == 200
    assert response.json()["boundary"] is None


def test_detail_rejects_invalid_uuid_and_returns_404_for_missing_record(registry_client):
    invalid = registry_client.get("/api/v1/water-bodies/not-a-uuid")
    missing = registry_client.get(f"/api/v1/water-bodies/{uuid4()}")
    assert invalid.status_code == 422
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Water body not found"}


def test_database_failure_returns_safe_service_error(registry_client, monkeypatch):
    def fail(*args, **kwargs):
        raise SQLAlchemyError("postgresql://sensitive-user:secret@localhost:5433/jalrakshak_test")

    monkeypatch.setattr(water_bodies, "list_water_bodies", fail)
    response = registry_client.get("/api/v1/water-bodies")
    assert response.status_code == 503
    assert response.json() == {"detail": "Water-body service is unavailable"}
    assert "sensitive-user" not in response.text and "secret" not in response.text
