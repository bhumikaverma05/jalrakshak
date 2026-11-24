"""Persistence and workflow rules for citizen reports."""

import json
from datetime import UTC, datetime, timedelta
from math import cos, radians
from typing import Any
from uuid import UUID

from geoalchemy2 import Geography
from geoalchemy2.elements import WKTElement
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AuditLog, CitizenReport, Evidence, User, WaterBody
from app.domains.audit.service import record_audit
from app.domains.evidence.service import evidence_response
from app.domains.reports.schemas import (
    AuditEntryResponse,
    CitizenReportPage,
    CitizenReportResponse,
    ReportCreate,
    ReportStatus,
    ReportUpdate,
)

ALLOWED_TRANSITIONS: dict[ReportStatus, set[ReportStatus]] = {
    ReportStatus.SUBMITTED: {ReportStatus.UNDER_REVIEW, ReportStatus.REJECTED},
    ReportStatus.UNDER_REVIEW: {ReportStatus.VERIFIED, ReportStatus.REJECTED},
    ReportStatus.VERIFIED: {ReportStatus.RESOLVED},
    ReportStatus.REJECTED: set(),
    ReportStatus.RESOLVED: set(),
}


class DuplicateReportError(Exception):
    def __init__(self, report_id: UUID):
        self.report_id = report_id


class ReportNotFoundError(Exception):
    pass


class WaterBodyNotFoundError(Exception):
    pass


class InvalidReportUpdateError(Exception):
    pass


def _point(longitude: float, latitude: float) -> WKTElement:
    return WKTElement(f"POINT({longitude:.10f} {latitude:.10f})", srid=4326)


def _is_duplicate(
    session: Session,
    *,
    request: ReportCreate,
    now: datetime,
) -> UUID | None:
    settings = get_settings()
    longitude, latitude = request.reported_location.coordinates
    point = _point(longitude, latitude)
    report_location = cast(CitizenReport.reported_location, Geography(srid=4326))
    candidate_location = cast(point, Geography(srid=4326))
    # Serialize same-category submissions in PostgreSQL so concurrent requests
    # cannot both pass the duplicate check before either inserts its report.
    session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(request.category.value, 0)))
    )
    latitude_delta = settings.report_duplicate_radius_m / 110_000
    longitude_delta = min(
        180,
        settings.report_duplicate_radius_m / (110_000 * max(cos(radians(latitude)), 0.000001)),
    )
    spatial_prefilter = CitizenReport.reported_location.op("&&")(
        func.ST_Expand(point, max(latitude_delta, longitude_delta))
    )
    return session.scalar(
        select(CitizenReport.id)
        .where(
            CitizenReport.category == request.category.value,
            CitizenReport.status != ReportStatus.REJECTED.value,
            CitizenReport.created_at
            >= now - timedelta(hours=settings.report_duplicate_window_hours),
            spatial_prefilter,
            func.ST_DWithin(
                report_location,
                candidate_location,
                settings.report_duplicate_radius_m,
            ),
        )
        .order_by(CitizenReport.created_at.desc(), CitizenReport.id)
        .limit(1)
    )


def create_report(
    session: Session,
    *,
    request: ReportCreate,
    reporter: User,
    now: datetime | None = None,
) -> CitizenReport:
    """Create an authenticated report or record a same-category duplicate attempt."""
    if request.water_body_id is not None and session.get(WaterBody, request.water_body_id) is None:
        raise WaterBodyNotFoundError

    timestamp = now or datetime.now(UTC)
    duplicate_id = _is_duplicate(session, request=request, now=timestamp)
    if duplicate_id is not None:
        record_audit(
            session,
            actor_id=reporter.id,
            action="citizen_report.duplicate_detected",
            entity_type="citizen_report",
            entity_id=duplicate_id,
            changes={
                "category": request.category.value,
                "window_hours": get_settings().report_duplicate_window_hours,
            },
        )
        session.flush()
        raise DuplicateReportError(duplicate_id)

    longitude, latitude = request.reported_location.coordinates
    report = CitizenReport(
        water_body_id=request.water_body_id,
        reporter_id=reporter.id,
        category=request.category.value,
        description=request.description,
        reported_location=_point(longitude, latitude),
        gps_accuracy_m=request.gps_accuracy_m,
        location_description=request.location_description,
        status=ReportStatus.SUBMITTED.value,
    )
    session.add(report)
    session.flush()
    record_audit(
        session,
        actor_id=reporter.id,
        action="citizen_report.submitted",
        entity_type="citizen_report",
        entity_id=report.id,
        changes={
            "status": {"from": None, "to": ReportStatus.SUBMITTED.value},
            "category": request.category.value,
            "water_body_id": str(report.water_body_id) if report.water_body_id else None,
        },
    )
    session.flush()
    return report


def report_response(session: Session, report: CitizenReport) -> CitizenReportResponse:
    point = session.scalar(
        select(func.ST_AsGeoJSON(CitizenReport.reported_location)).where(
            CitizenReport.id == report.id
        )
    )
    evidence = session.scalars(
        select(Evidence)
        .where(Evidence.citizen_report_id == report.id)
        .order_by(Evidence.uploaded_at, Evidence.id)
    ).all()
    return CitizenReportResponse(
        id=report.id,
        water_body_id=report.water_body_id,
        reporter_id=report.reporter_id,
        assigned_to=report.assigned_to,
        category=report.category,
        description=report.description,
        reported_location=json.loads(point),
        gps_accuracy_m=report.gps_accuracy_m,
        location_description=report.location_description,
        status=(ReportStatus.UNDER_REVIEW.value if report.status == "assigned" else report.status),
        created_at=report.created_at,
        updated_at=report.updated_at,
        evidence=[evidence_response(session, item) for item in evidence],
    )


def list_reports(
    session: Session,
    *,
    actor: User,
    page: int,
    page_size: int,
    status: ReportStatus | None = None,
    water_body_id: UUID | None = None,
) -> CitizenReportPage:
    query = select(CitizenReport)
    count_query = select(func.count()).select_from(CitizenReport)
    if actor.role == "citizen":
        query = query.where(CitizenReport.reporter_id == actor.id)
        count_query = count_query.where(CitizenReport.reporter_id == actor.id)
    if status is not None:
        query = query.where(CitizenReport.status == status.value)
        count_query = count_query.where(CitizenReport.status == status.value)
    if water_body_id is not None:
        query = query.where(CitizenReport.water_body_id == water_body_id)
        count_query = count_query.where(CitizenReport.water_body_id == water_body_id)
    total = session.scalar(count_query) or 0
    reports = session.scalars(
        query.order_by(CitizenReport.created_at.desc(), CitizenReport.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return CitizenReportPage(
        items=[report_response(session, report) for report in reports],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_report(session: Session, *, report_id: UUID, actor: User) -> CitizenReport | None:
    report = session.get(CitizenReport, report_id)
    if report is None or (actor.role == "citizen" and report.reporter_id != actor.id):
        return None
    return report


def get_report_audit(session: Session, report_id: UUID) -> list[AuditEntryResponse]:
    rows = session.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "citizen_report", AuditLog.entity_id == report_id)
        .order_by(AuditLog.created_at, AuditLog.id)
    ).all()
    return [
        AuditEntryResponse(
            id=row.id,
            actor_id=row.actor_id,
            action=row.action,
            changes=row.changes,
            created_at=row.created_at,
        )
        for row in rows
    ]


def update_report(
    session: Session,
    *,
    report_id: UUID,
    actor: User,
    request: ReportUpdate,
) -> CitizenReport:
    # Serialize concurrent reviewer updates so each transition is validated
    # against the latest committed state and its audit diff stays accurate.
    report = session.scalar(
        select(CitizenReport).where(CitizenReport.id == report_id).with_for_update()
    )
    if report is None:
        raise ReportNotFoundError

    changes: dict[str, Any] = {}
    if request.status is not None:
        current = (
            ReportStatus.UNDER_REVIEW
            if report.status == "assigned"
            else ReportStatus(report.status)
        )
        if request.status not in ALLOWED_TRANSITIONS[current]:
            raise InvalidReportUpdateError("Invalid report status transition")
        changes["status"] = {"from": current.value, "to": request.status.value}
        report.status = request.status.value

    if "assigned_to" in request.model_fields_set:
        target_id = request.assigned_to
        if target_id is not None:
            if report.status != ReportStatus.UNDER_REVIEW.value:
                raise InvalidReportUpdateError("Reports must be under review before assignment")
            target = session.get(User, target_id)
            if target is None or not target.is_active or target.role not in {"officer", "engineer"}:
                raise InvalidReportUpdateError("Assignee must be an active officer or engineer")
        if report.assigned_to != target_id:
            changes["assigned_to"] = {
                "from": str(report.assigned_to) if report.assigned_to else None,
                "to": str(target_id) if target_id else None,
            }
            report.assigned_to = target_id

    if "water_body_id" in request.model_fields_set:
        target_water_body_id = request.water_body_id
        if (
            target_water_body_id is not None
            and session.get(WaterBody, target_water_body_id) is None
        ):
            raise WaterBodyNotFoundError
        if report.water_body_id != target_water_body_id:
            changes["water_body_id"] = {
                "from": str(report.water_body_id) if report.water_body_id else None,
                "to": str(target_water_body_id) if target_water_body_id else None,
            }
            report.water_body_id = target_water_body_id

    if not changes:
        raise InvalidReportUpdateError("The requested update makes no change")
    if request.review_note:
        changes["review_note"] = request.review_note
    session.flush()
    record_audit(
        session,
        actor_id=actor.id,
        action="citizen_report.review_updated",
        entity_type="citizen_report",
        entity_id=report.id,
        changes=changes,
    )
    session.flush()
    return report
