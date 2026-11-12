from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import OptionalUser, Permission, has_permission
from app.db import get_db
from app.models import AuditLog, User
from app.schemas import AuditRead

router = APIRouter(prefix="/audit", tags=["audit"])
DbDep = Annotated[Session, Depends(get_db)]

# Entity types whose history is as private as the entities themselves.
_RESTRICTED: dict[str, Permission] = {
    "field_report": Permission.VIEW_REPORTS,  # locations and informant details
    "user": Permission.MANAGE_USERS,
}


def hidden_entity_types(user: User | None) -> list[str]:
    return [
        entity
        for entity, permission in _RESTRICTED.items()
        if user is None or not has_permission(user, permission)
    ]


@router.get("", response_model=list[AuditRead])
def list_audit(
    db: DbDep,
    user: OptionalUser,
    entity_type: str | None = None,
    entity_id: int | None = None,
    source: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditLog]:
    """Newest first. `source` filters e.g. `api` or `import:<uuid>`.

    Public for hazard data; history of field reports and users needs the same permission
    as the records themselves.
    """
    stmt = select(AuditLog)
    if hidden := hidden_entity_types(user):
        stmt = stmt.where(AuditLog.entity_type.not_in(hidden))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if source:
        stmt = stmt.where(AuditLog.source == source)
    stmt = stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())
