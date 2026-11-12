from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditLog
from app.schemas import AuditRead

router = APIRouter(prefix="/audit", tags=["audit"])
DbDep = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[AuditRead])
def list_audit(
    db: DbDep,
    entity_type: str | None = None,
    entity_id: int | None = None,
    source: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditLog]:
    """Newest first. `source` filters e.g. `api` or `import:<uuid>`."""
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if source:
        stmt = stmt.where(AuditLog.source == source)
    stmt = stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())
