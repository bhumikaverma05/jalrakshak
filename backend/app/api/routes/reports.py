"""Citizen-report submission, retrieval, review, and evidence endpoints."""

from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import CitizenReport, Evidence, User
from app.db.session import get_session
from app.domains.audit.service import record_audit
from app.domains.auth.dependencies import require_citizen, require_roles
from app.domains.evidence.schemas import EvidenceResponse
from app.domains.evidence.service import (
    EvidenceNotFoundError,
    EvidenceStorageError,
    EvidenceValidationError,
    evidence_path,
    save_report_evidence,
)
from app.domains.reports.schemas import (
    AuditEntryResponse,
    CitizenReportPage,
    CitizenReportResponse,
    ReportCreate,
    ReportStatus,
    ReportUpdate,
)
from app.domains.reports.service import (
    DuplicateReportError,
    InvalidReportUpdateError,
    ReportNotFoundError,
    WaterBodyNotFoundError,
    create_report,
    get_report,
    get_report_audit,
    list_reports,
    report_response,
    update_report,
)

router = APIRouter()
ReportReader = Annotated[
    User,
    Depends(require_roles("citizen", "officer", "engineer", "administrator")),
]
ReportReviewer = Annotated[User, Depends(require_roles("officer", "engineer", "administrator"))]


@router.post(
    "",
    response_model=CitizenReportResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "A same-category duplicate report was detected"}},
    summary="Submit a citizen report",
)
def submit_report(
    request: ReportCreate,
    session: Annotated[Session, Depends(get_session)],
    citizen: Annotated[User, Depends(require_citizen)],
) -> CitizenReportResponse | JSONResponse:
    try:
        report = create_report(session, request=request, reporter=citizen)
        return report_response(session, report)
    except DuplicateReportError:
        # Return normally so the duplicate-attempt audit row commits in this transaction.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "A similar report was submitted recently", "duplicate": True},
        )
    except WaterBodyNotFoundError:
        raise HTTPException(status_code=404, detail="Water body not found") from None
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Report service is unavailable") from None


@router.get("", response_model=CitizenReportPage, summary="List citizen reports")
def read_reports(
    session: Annotated[Session, Depends(get_session)],
    actor: ReportReader,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    report_status: Annotated[ReportStatus | None, Query(alias="status")] = None,
    water_body_id: UUID | None = None,
) -> CitizenReportPage:
    try:
        return list_reports(
            session,
            actor=actor,
            page=page,
            page_size=page_size,
            status=report_status,
            water_body_id=water_body_id,
        )
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Report service is unavailable") from None


@router.get("/{report_id}", response_model=CitizenReportResponse, summary="Get a citizen report")
def read_report(
    report_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    actor: ReportReader,
) -> CitizenReportResponse:
    try:
        report = get_report(session, report_id=report_id, actor=actor)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return report_response(session, report)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Report service is unavailable") from None


@router.patch(
    "/{report_id}", response_model=CitizenReportResponse, summary="Review a citizen report"
)
def review_report(
    report_id: UUID,
    request: ReportUpdate,
    session: Annotated[Session, Depends(get_session)],
    reviewer: ReportReviewer,
) -> CitizenReportResponse:
    try:
        report = update_report(session, report_id=report_id, actor=reviewer, request=request)
        return report_response(session, report)
    except ReportNotFoundError:
        raise HTTPException(status_code=404, detail="Report not found") from None
    except InvalidReportUpdateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except WaterBodyNotFoundError:
        raise HTTPException(status_code=404, detail="Water body not found") from None
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Report service is unavailable") from None


@router.get(
    "/{report_id}/audit",
    response_model=list[AuditEntryResponse],
    summary="Get a report audit history",
)
def read_report_audit(
    report_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    reviewer: ReportReviewer,
) -> list[AuditEntryResponse]:
    try:
        if session.get(CitizenReport, report_id) is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return get_report_audit(session, report_id)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Report service is unavailable") from None


@router.post(
    "/{report_id}/evidence",
    response_model=EvidenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload photo evidence for a citizen report",
)
def upload_report_evidence(
    report_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    actor: ReportReader,
    file: Annotated[UploadFile, File(description="JPEG, PNG, or WebP image")],
    captured_at: Annotated[datetime | None, Form()] = None,
    gps_longitude: Annotated[float | None, Form(ge=-180, le=180)] = None,
    gps_latitude: Annotated[float | None, Form(ge=-90, le=90)] = None,
):
    try:
        report = get_report(session, report_id=report_id, actor=actor)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        if actor.role == "citizen" and report.reporter_id != actor.id:
            raise HTTPException(status_code=404, detail="Report not found")
        max_size = get_settings().evidence_max_size_bytes
        data = file.file.read(max_size + 1)
        if len(data) > max_size:
            raise HTTPException(status_code=413, detail="Evidence exceeds the upload size limit")
        item = save_report_evidence(
            session,
            report=report,
            actor=actor,
            data=data,
            original_filename=file.filename or "evidence",
            captured_at=captured_at,
            gps_longitude=gps_longitude,
            gps_latitude=gps_latitude,
        )
        from app.domains.evidence.service import evidence_response

        return evidence_response(session, item)
    except EvidenceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ModuleNotFoundError:
        raise HTTPException(
            status_code=503, detail="Image validation dependency is unavailable"
        ) from None
    except EvidenceStorageError:
        raise HTTPException(status_code=503, detail="Evidence storage is unavailable") from None
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Evidence service is unavailable") from None
    finally:
        file.file.close()


@router.get(
    "/{report_id}/evidence/{evidence_id}",
    response_class=FileResponse,
    summary="Download report evidence",
)
def download_report_evidence(
    report_id: UUID,
    evidence_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    actor: ReportReader,
) -> FileResponse:
    try:
        report = get_report(session, report_id=report_id, actor=actor)
        if report is None:
            raise HTTPException(status_code=404, detail="Evidence not found")
        item = session.scalar(
            select(Evidence).where(
                Evidence.id == evidence_id,
                Evidence.citizen_report_id == report.id,
            )
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Evidence not found")
        path = evidence_path(item.storage_key)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Evidence not found")
        record_audit(
            session,
            actor_id=actor.id,
            action="citizen_report.evidence_downloaded",
            entity_type="citizen_report",
            entity_id=report.id,
            changes={"evidence_id": str(item.id)},
        )
        return FileResponse(
            path,
            media_type=item.mime_type,
            filename=Path(item.original_filename).name,
            content_disposition_type="attachment",
        )
    except EvidenceNotFoundError:
        raise HTTPException(status_code=404, detail="Evidence not found") from None
    except EvidenceStorageError:
        raise HTTPException(status_code=503, detail="Evidence storage is unavailable") from None
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Evidence service is unavailable") from None
