"""Evidence response contract."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class EvidenceResponse(BaseModel):
    id: UUID
    original_filename: str
    mime_type: str
    file_size_bytes: int
    checksum_sha256: str | None
    captured_at: datetime | None
    gps_location: dict[str, Any] | None
    uploaded_at: datetime
