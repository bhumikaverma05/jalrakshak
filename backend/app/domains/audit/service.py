"""Small audit-log writer shared by report operations."""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def record_audit(
    session: Session,
    *,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID,
    changes: dict[str, Any],
) -> AuditLog:
    """Queue an audit row in the caller's transaction."""
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
    )
    session.add(entry)
    return entry
