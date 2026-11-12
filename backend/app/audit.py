"""Audit trail helpers. Callers commit; audit rows share the caller's transaction."""

from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


def record(
    db: Session,
    entity_type: str,
    entity_id: int,
    action: str,
    changes: dict[str, Any] | None = None,
    source: str = "api",
) -> None:
    db.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            changes=changes or {},
            source=source,
        )
    )


def diff(obj: Any, new_values: dict[str, Any]) -> dict[str, list[Any]]:
    """Fields whose value would change: {field: [old, new]}. Call before applying."""
    return {
        field: [_jsonable(getattr(obj, field)), _jsonable(value)]
        for field, value in new_values.items()
        if getattr(obj, field) != value
    }


def created_values(values: dict[str, Any]) -> dict[str, list[Any]]:
    return {field: [None, _jsonable(value)] for field, value in values.items()}
