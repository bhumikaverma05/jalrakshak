"""Image validation and local evidence storage for citizen reports."""

import re
import warnings
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import CitizenReport, Evidence, User
from app.domains.audit.service import record_audit
from app.domains.evidence.schemas import EvidenceResponse

ALLOWED_IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}
MAX_IMAGE_PIXELS = 25_000_000


class EvidenceValidationError(Exception):
    pass


class EvidenceNotFoundError(Exception):
    pass


class EvidenceStorageError(Exception):
    pass


def _normalized_image(data: bytes) -> tuple[bytes, str, str]:
    from PIL import Image, ImageOps

    if not data:
        raise EvidenceValidationError("The uploaded file is empty")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                source_format = image.format
                if source_format not in ALLOWED_IMAGE_FORMATS:
                    raise EvidenceValidationError("Only JPEG, PNG, and WebP images are accepted")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise EvidenceValidationError("The image dimensions exceed the allowed limit")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
                image = ImageOps.exif_transpose(image)
                mime_type, extension = ALLOWED_IMAGE_FORMATS[source_format]
                output = BytesIO()
                if source_format == "JPEG":
                    image = image.convert("RGB")
                image.save(output, format=source_format, optimize=True)
                clean_data = output.getvalue()
    except EvidenceValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        ValueError,
    ):
        raise EvidenceValidationError("The uploaded file is not a valid supported image") from None
    if len(clean_data) > get_settings().evidence_max_size_bytes:
        raise EvidenceValidationError("The processed image exceeds the upload size limit")
    return clean_data, mime_type, extension


def _storage_root() -> Path:
    try:
        root = get_settings().evidence_storage_dir.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root
    except (OSError, RuntimeError):
        raise EvidenceStorageError("Evidence storage is unavailable") from None


def evidence_path(storage_key: str) -> Path:
    root = _storage_root()
    try:
        candidate = (root / storage_key).resolve()
    except (OSError, RuntimeError):
        raise EvidenceStorageError("Evidence storage is unavailable") from None
    try:
        candidate.relative_to(root)
    except ValueError:
        raise EvidenceNotFoundError from None
    return candidate


def cleanup_pending_files(session: Session) -> None:
    for path in session.info.pop("pending_evidence_files", []):
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            # Keep rollback handling best effort; paths are opaque and confined to our upload root.
            continue


def save_report_evidence(
    session: Session,
    *,
    report: CitizenReport,
    actor: User,
    data: bytes,
    original_filename: str,
    captured_at: datetime | None,
    gps_longitude: float | None,
    gps_latitude: float | None,
) -> Evidence:
    clean_data, mime_type, extension = _normalized_image(data)
    if (gps_longitude is None) != (gps_latitude is None):
        raise EvidenceValidationError("Provide both GPS coordinates or neither")
    if gps_longitude is not None and not (-180 <= gps_longitude <= 180):
        raise EvidenceValidationError("GPS longitude must be between -180 and 180")
    if gps_latitude is not None and not (-90 <= gps_latitude <= 90):
        raise EvidenceValidationError("GPS latitude must be between -90 and 90")
    if captured_at is not None and captured_at.utcoffset() is None:
        raise EvidenceValidationError("Capture timestamp must include a timezone")

    if gps_longitude is None or gps_latitude is None:
        longitude, latitude = session.execute(
            select(
                func.ST_X(CitizenReport.reported_location),
                func.ST_Y(CitizenReport.reported_location),
            ).where(CitizenReport.id == report.id)
        ).one()
        gps_longitude, gps_latitude = float(longitude), float(latitude)

    supplied_name = (original_filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    safe_name = re.sub(r"[^\w .()\-]", "_", supplied_name, flags=re.UNICODE).strip(" .")
    safe_name = (safe_name or f"evidence{extension}")[:255]
    storage_key = f"{uuid4().hex}{extension}"
    path = evidence_path(storage_key)
    try:
        with path.open("xb") as file_handle:
            # Register immediately after exclusive creation so partial writes and
            # close failures are also cleaned up on transaction rollback.
            session.info.setdefault("pending_evidence_files", []).append(path)
            file_handle.write(clean_data)
        item = Evidence(
            citizen_report_id=report.id,
            uploaded_by=actor.id,
            storage_key=storage_key,
            original_filename=safe_name,
            mime_type=mime_type,
            file_size_bytes=len(clean_data),
            checksum_sha256=sha256(clean_data).hexdigest(),
            captured_at=captured_at,
            gps_location=WKTElement(f"POINT({gps_longitude:.10f} {gps_latitude:.10f})", srid=4326),
            metadata_validation_status="validated",
        )
        session.add(item)
        session.flush()
        record_audit(
            session,
            actor_id=actor.id,
            action="citizen_report.evidence_uploaded",
            entity_type="citizen_report",
            entity_id=report.id,
            changes={
                "evidence_id": str(item.id),
                "mime_type": mime_type,
                "file_size_bytes": item.file_size_bytes,
                "checksum_sha256": item.checksum_sha256,
            },
        )
        session.flush()
    except Exception as exc:
        pending = session.info.get("pending_evidence_files", [])
        if path in pending:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                # Leave the path registered so request rollback can retry cleanup.
                pass
            else:
                pending.remove(path)
        if isinstance(exc, OSError):
            raise EvidenceStorageError("Evidence storage is unavailable") from None
        raise
    return item


def evidence_response(session: Session, item: Evidence) -> EvidenceResponse:
    import json

    geojson = session.scalar(
        select(func.ST_AsGeoJSON(Evidence.gps_location)).where(Evidence.id == item.id)
    )
    return EvidenceResponse(
        id=item.id,
        original_filename=item.original_filename,
        mime_type=item.mime_type,
        file_size_bytes=item.file_size_bytes,
        checksum_sha256=item.checksum_sha256,
        captured_at=item.captured_at,
        gps_location=json.loads(geojson) if geojson else None,
        uploaded_at=item.uploaded_at,
    )
