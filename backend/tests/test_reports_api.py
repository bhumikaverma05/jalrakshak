"""Citizen-report API and workflow coverage against the isolated test database."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, CitizenReport, User
from app.domains.auth.security import create_access_token
from app.domains.reports.schemas import GeoJSONPoint, ReportCategory, ReportCreate, ReportStatus
from app.domains.reports.service import ALLOWED_TRANSITIONS
from app.main import app


def _user(session: Session, role: str) -> User:
    user = User(
        email=f"{uuid4()}@example.test",
        full_name=f"{role.title()} Test User",
        password_hash="test-only-hash",
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


@pytest.fixture
def reports_client(db_session: Session):
    from app.db.session import get_session

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _payload(*, category: str = "garbage_dumping", longitude: float = 77.4) -> dict:
    return {
        "category": category,
        "description": "Waste dumped beside the pond",
        "reported_location": {"type": "Point", "coordinates": [longitude, 23.2]},
        "gps_accuracy_m": 8.5,
    }


def test_create_requires_citizen_and_sets_server_owned_fields(reports_client, db_session):
    citizen = _user(db_session, "citizen")
    officer = _user(db_session, "officer")
    unauthenticated = reports_client.post("/api/v1/reports", json=_payload())
    wrong_role = reports_client.post("/api/v1/reports", json=_payload(), headers=_headers(officer))
    created = reports_client.post("/api/v1/reports", json=_payload(), headers=_headers(citizen))

    assert unauthenticated.status_code == 401
    assert wrong_role.status_code == 403
    assert created.status_code == 201
    body = created.json()
    assert body["reporter_id"] == str(citizen.id)
    assert body["status"] == "submitted"
    assert body["category"] == "garbage_dumping"
    assert (session_report := db_session.get(CitizenReport, body["id"]))
    assert session_report.reporter_id == citizen.id
    assert (
        db_session.scalar(select(AuditLog).where(AuditLog.entity_id == session_report.id)).action
        == "citizen_report.submitted"
    )


def test_create_validates_categories_coordinates_and_client_controlled_fields(
    reports_client, db_session
):
    citizen = _user(db_session, "citizen")
    headers = _headers(citizen)
    invalid_category = reports_client.post(
        "/api/v1/reports", json=_payload(category="dumping"), headers=headers
    )
    invalid_coordinate = _payload()
    invalid_coordinate["reported_location"]["coordinates"] = [181, 23]
    invalid_point = reports_client.post("/api/v1/reports", json=invalid_coordinate, headers=headers)
    role_escalation = _payload()
    role_escalation["reporter_id"] = str(uuid4())
    forged_status = reports_client.post("/api/v1/reports", json=role_escalation, headers=headers)

    assert invalid_category.status_code == 422
    assert invalid_point.status_code == 422
    assert forged_status.status_code == 422


def test_duplicate_detection_uses_same_category_radius_and_window(reports_client, db_session):
    citizen = _user(db_session, "citizen")
    headers = _headers(citizen)
    first = reports_client.post("/api/v1/reports", json=_payload(), headers=headers)
    nearby_same_category = reports_client.post(
        "/api/v1/reports",
        json=_payload(longitude=77.4002),
        headers=headers,
    )
    other_category = reports_client.post(
        "/api/v1/reports",
        json=_payload(category="plastic_pollution", longitude=77.4002),
        headers=headers,
    )
    outside_radius = reports_client.post(
        "/api/v1/reports", json=_payload(longitude=77.41), headers=headers
    )

    assert first.status_code == 201
    assert nearby_same_category.status_code == 409
    assert nearby_same_category.json()["duplicate"] is True
    assert other_category.status_code == 201
    assert outside_radius.status_code == 201
    first_record = db_session.get(CitizenReport, first.json()["id"])
    first_record.created_at = datetime.now(UTC) - timedelta(hours=25)
    db_session.flush()
    outside_window = reports_client.post("/api/v1/reports", json=_payload(), headers=headers)
    assert outside_window.status_code == 201
    duplicate_audit = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "citizen_report.duplicate_detected")
    )
    assert duplicate_audit is not None


def test_citizen_visibility_staff_review_and_audit_history(reports_client, db_session):
    citizen = _user(db_session, "citizen")
    other_citizen = _user(db_session, "citizen")
    officer = _user(db_session, "officer")
    engineer = _user(db_session, "engineer")
    created = reports_client.post("/api/v1/reports", json=_payload(), headers=_headers(citizen))
    report_id = created.json()["id"]

    hidden = reports_client.get(f"/api/v1/reports/{report_id}", headers=_headers(other_citizen))
    citizen_review = reports_client.patch(
        f"/api/v1/reports/{report_id}",
        json={"status": "under_review"},
        headers=_headers(citizen),
    )
    started = reports_client.patch(
        f"/api/v1/reports/{report_id}",
        json={"status": "under_review", "assigned_to": str(engineer.id)},
        headers=_headers(officer),
    )
    verified = reports_client.patch(
        f"/api/v1/reports/{report_id}",
        json={"status": "verified"},
        headers=_headers(officer),
    )
    resolved = reports_client.patch(
        f"/api/v1/reports/{report_id}",
        json={"status": "resolved"},
        headers=_headers(engineer),
    )
    audit = reports_client.get(f"/api/v1/reports/{report_id}/audit", headers=_headers(engineer))
    own_list = reports_client.get("/api/v1/reports", headers=_headers(citizen))
    staff_list = reports_client.get("/api/v1/reports", headers=_headers(officer))

    assert hidden.status_code == 404
    assert citizen_review.status_code == 403
    assert started.status_code == 200
    assert started.json()["status"] == "under_review"
    assert started.json()["assigned_to"] == str(engineer.id)
    assert verified.status_code == 200
    assert verified.json()["status"] == "verified"
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    terminal_update = reports_client.patch(
        f"/api/v1/reports/{report_id}",
        json={"status": "under_review"},
        headers=_headers(officer),
    )
    assert terminal_update.status_code == 409
    assert audit.status_code == 200
    assert {entry["action"] for entry in audit.json()} >= {
        "citizen_report.submitted",
        "citizen_report.review_updated",
    }
    assert own_list.json()["total"] == 1
    assert staff_list.json()["total"] == 1


def test_transition_graph_is_restricted():
    assert ALLOWED_TRANSITIONS[ReportStatus.SUBMITTED] == {
        ReportStatus.UNDER_REVIEW,
        ReportStatus.REJECTED,
    }
    assert ALLOWED_TRANSITIONS[ReportStatus.UNDER_REVIEW] == {
        ReportStatus.VERIFIED,
        ReportStatus.REJECTED,
    }
    assert ALLOWED_TRANSITIONS[ReportStatus.VERIFIED] == {ReportStatus.RESOLVED}
    assert not ALLOWED_TRANSITIONS[ReportStatus.REJECTED]
    assert not ALLOWED_TRANSITIONS[ReportStatus.RESOLVED]


def test_report_schema_accepts_only_wgs84_point_categories():
    valid = ReportCreate(
        category=ReportCategory.FOUL_SMELL,
        description="Odour near the water body",
        reported_location=GeoJSONPoint(coordinates=(77.4, 23.2)),
    )
    assert valid.reported_location.coordinates == (77.4, 23.2)
    with pytest.raises(ValueError):
        GeoJSONPoint(coordinates=(181, 23.2))


def test_report_evidence_upload_is_validated_and_private(
    reports_client, db_session, monkeypatch, tmp_path
):
    from io import BytesIO

    pytest.importorskip("PIL")

    from PIL import Image

    from app.core.config import get_settings

    monkeypatch.setenv("EVIDENCE_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()
    citizen = _user(db_session, "citizen")
    created = reports_client.post("/api/v1/reports", json=_payload(), headers=_headers(citizen))
    image = BytesIO()
    Image.new("RGB", (3, 3), "blue").save(image, format="PNG")
    uploaded = reports_client.post(
        f"/api/v1/reports/{created.json()['id']}/evidence",
        files={"file": ("../../water.png", image.getvalue(), "image/png")},
        data={"captured_at": "2026-11-24T12:00:00Z"},
        headers=_headers(citizen),
    )
    get_settings.cache_clear()

    assert uploaded.status_code == 201
    evidence = uploaded.json()
    assert evidence["mime_type"] == "image/png"
    assert evidence["gps_location"]["coordinates"] == [77.4, 23.2]
    assert evidence["captured_at"].startswith("2026-11-24T12:00:00")
    assert list(tmp_path.iterdir())
    invalid_image = reports_client.post(
        f"/api/v1/reports/{created.json()['id']}/evidence",
        files={"file": ("broken.png", b"not an image", "image/png")},
        headers=_headers(citizen),
    )
    assert invalid_image.status_code == 422
    assert len(list(tmp_path.iterdir())) == 1
    download = reports_client.get(
        f"/api/v1/reports/{created.json()['id']}/evidence/{evidence['id']}",
        headers=_headers(citizen),
    )
    assert download.status_code == 200
    assert download.content.startswith(b"\x89PNG")
    another_citizen = _user(db_session, "citizen")
    private_download = reports_client.get(
        f"/api/v1/reports/{created.json()['id']}/evidence/{evidence['id']}",
        headers=_headers(another_citizen),
    )
    assert private_download.status_code == 404
    evidence_actions = set(
        db_session.scalars(
            select(AuditLog.action).where(AuditLog.entity_id == UUID(created.json()["id"]))
        ).all()
    )
    assert "citizen_report.evidence_uploaded" in evidence_actions
    assert "citizen_report.evidence_downloaded" in evidence_actions


def test_evidence_path_rejects_traversal(monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.domains.evidence.service import EvidenceNotFoundError, evidence_path

    monkeypatch.setenv("EVIDENCE_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        with pytest.raises(EvidenceNotFoundError):
            evidence_path("../outside.jpg")
    finally:
        get_settings.cache_clear()


def test_evidence_storage_unavailable_is_reported_safely(monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.domains.evidence.service import EvidenceStorageError, evidence_path

    not_a_directory = tmp_path / "occupied"
    not_a_directory.write_text("file", encoding="utf-8")
    monkeypatch.setenv("EVIDENCE_STORAGE_DIR", str(not_a_directory))
    get_settings.cache_clear()
    try:
        with pytest.raises(EvidenceStorageError):
            evidence_path("image.jpg")
    finally:
        get_settings.cache_clear()
