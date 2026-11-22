"""PostgreSQL/PostGIS schema, model, constraint, and spatial integration checks."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from geoalchemy2.elements import WKTElement
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.db.base import Base
from app.db.models import (
    AuditLog,
    CitizenReport,
    Evidence,
    FieldObservation,
    PreliminaryAssessment,
    SatelliteObservation,
    User,
    WaterBody,
    WaterQualityReading,
)

pytestmark = pytest.mark.postgres


def _user(session: Session) -> User:
    value = User(
        email=f"{uuid4()}@example.test",
        full_name="Test Operator",
        password_hash="test-hash",
        role="engineer",
    )
    session.add(value)
    session.flush()
    return value


def _water(session: Session, *, polygon: bool = False) -> WaterBody:
    value = WaterBody(
        water_body_code=f"TEST-{uuid4()}",
        name="Synthetic Test Pond",
        water_body_type="pond",
        district="Test District",
        state="Test State",
        location=WKTElement("POINT(77.4 23.2)", srid=4326),
        boundary=WKTElement(
            "MULTIPOLYGON(((77.3 23.1,77.5 23.1,77.5 23.3,77.3 23.3,77.3 23.1)))", srid=4326
        )
        if polygon
        else None,
        source_metadata={"test_fixture": True},
    )
    session.add(value)
    session.flush()
    return value


def test_postgis_connectivity_and_migration_head(postgres_engine):
    with postgres_engine.connect() as connection:
        assert connection.execute(text("SELECT current_database()")).scalar_one().endswith("_test")
        assert connection.execute(text("SHOW server_version")).scalar_one()
        assert connection.execute(text("SELECT PostGIS_Full_Version()")).scalar_one()
        assert connection.execute(text("SELECT PostGIS_Version()")).scalar_one()
        tables = set(inspect(connection).get_table_names())
        assert set(Base.metadata.tables).issubset(tables)
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "20261122_0001"
        )
        spatial_indexes = [
            index
            for table in Base.metadata.tables
            for index in inspect(connection).get_indexes(table)
            if index.get("dialect_options", {}).get("postgresql_using") == "gist"
        ]
        assert len(spatial_indexes) >= 5


def test_model_creation_and_nullable_unregistered_report(db_session):
    user = _user(db_session)
    water = _water(db_session, polygon=True)
    report = CitizenReport(
        category="pollution",
        description="Synthetic test report",
        reported_location=WKTElement("POINT(77.41 23.21)", srid=4326),
        reporter_id=user.id,
    )
    observation = FieldObservation(
        water_body_id=water.id,
        observer_id=user.id,
        observed_at=datetime.now(UTC),
        observation_location=WKTElement("POINT(77.4 23.2)", srid=4326),
        description="synthetic",
    )
    db_session.add_all([report, observation])
    db_session.flush()
    evidence = Evidence(
        field_observation_id=observation.id,
        uploaded_by=user.id,
        storage_key=f"test/{uuid4()}",
        original_filename="synthetic.jpg",
        mime_type="image/jpeg",
        file_size_bytes=1,
    )
    assessment = PreliminaryAssessment(
        water_body_id=water.id,
        assessed_by=user.id,
        assessment_date=date.today(),
        garbage_score=1,
        algal_stress_score=1,
        sewage_score=1,
        encroachment_score=1,
        shrinkage_score=1,
        total_degradation_score=5,
    )
    quality = WaterQualityReading(
        water_body_id=water.id,
        recorded_by=user.id,
        reading_at=datetime.now(UTC),
        ph=Decimal("7.00"),
        source="synthetic test",
        is_simulated=True,
    )
    satellite = SatelliteObservation(
        water_body_id=water.id,
        recorded_by=user.id,
        satellite="test",
        scene_id=f"scene-{uuid4()}",
        acquired_at=datetime.now(UTC),
        cloud_percentage=Decimal("10.0"),
    )
    audit = AuditLog(
        actor_id=user.id,
        action="test",
        entity_type="water_body",
        entity_id=water.id,
        changes={"synthetic": True},
    )
    db_session.add_all([evidence, assessment, quality, satellite, audit])
    db_session.flush()
    assert report.water_body_id is None
    assert len(Base.metadata.tables) == 9


def test_unique_email_score_cloud_and_foreign_key_constraints(db_session):
    user = _user(db_session)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            User(
                email=user.email.upper(),
                full_name="Duplicate",
                password_hash="hash",
                role="citizen",
            )
        )
        db_session.flush()
    user = _user(db_session)
    water = _water(db_session)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            PreliminaryAssessment(
                water_body_id=water.id,
                assessed_by=user.id,
                assessment_date=date.today(),
                garbage_score=9,
                algal_stress_score=0,
                sewage_score=0,
                encroachment_score=0,
                shrinkage_score=0,
                total_degradation_score=9,
            )
        )
        db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            SatelliteObservation(
                water_body_id=water.id,
                satellite="test",
                scene_id="cloud-invalid",
                acquired_at=datetime.now(UTC),
                cloud_percentage=Decimal(101),
            )
        )
        db_session.flush()


def test_foreign_keys_duplicate_scene_and_restrict_delete(db_session):
    user = _user(db_session)
    water = _water(db_session)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            FieldObservation(
                water_body_id=uuid4(), observer_id=user.id, observed_at=datetime.now(UTC)
            )
        )
        db_session.flush()
    scene = SatelliteObservation(
        water_body_id=water.id,
        satellite="test",
        scene_id="unique-scene",
        acquired_at=datetime.now(UTC),
        cloud_percentage=Decimal(20),
    )
    db_session.add(scene)
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            SatelliteObservation(
                water_body_id=water.id,
                satellite="test",
                scene_id="unique-scene",
                acquired_at=datetime.now(UTC),
                cloud_percentage=Decimal(20),
            )
        )
        db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.delete(water)
        db_session.flush()


def test_invalid_boundary_is_rejected(db_session):
    with pytest.raises(IntegrityError), db_session.begin_nested():
        value = WaterBody(
            water_body_code=f"INVALID-{uuid4()}",
            name="Invalid Geometry",
            water_body_type="pond",
            district="Test District",
            state="Test State",
            location=WKTElement("POINT(77.4 23.2)", srid=4326),
            boundary=WKTElement("MULTIPOLYGON(((0 0,2 2,0 2,2 0,0 0)))", srid=4326),
        )
        db_session.add(value)
        db_session.flush()


def test_spatial_types_srid_geojson_and_predicates(db_session):
    water = _water(db_session, polygon=True)
    result = db_session.execute(
        text("""
        SELECT ST_SRID(location), GeometryType(location), ST_SRID(boundary),
               ST_Within(ST_SetSRID(ST_MakePoint(77.4,23.2),4326), boundary),
               ST_Within(ST_SetSRID(ST_MakePoint(78,24),4326), boundary),
               ST_Intersects(location,boundary), ST_AsGeoJSON(location),
               ST_Area(ST_Transform(boundary,32643))
        FROM water_bodies WHERE id=:id
    """),
        {"id": water.id},
    ).one()
    assert result[0:3] == (4326, "POINT", 4326)
    assert result[3] is True and result[4] is False and result[5] is True
    assert '"coordinates":[77.4,23.2]' in result[6]
    assert result[7] > 0


def test_z_migration_downgrade_and_upgrade_on_disposable_database(postgres_engine):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    with postgres_engine.connect() as connection:
        assert set(Base.metadata.tables).issubset(set(inspect(connection).get_table_names()))
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "20261122_0001"
        )
