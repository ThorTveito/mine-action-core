from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app import audit
from app.auth import Permission, require
from app.db import get_db
from app.models import QaInspection, Task, TaskStatus, TaskType, User
from app.schemas import QaInspectionCreate, QaInspectionRead

router = APIRouter(prefix="/qa-inspections", tags=["qa"])
DbDep = Annotated[Session, Depends(get_db)]


def _get_or_404(db: Session, inspection_id: int) -> QaInspection:
    inspection = db.get(QaInspection, inspection_id)
    if inspection is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Inspection {inspection_id} not found"
        )
    return inspection


@router.get("", response_model=list[QaInspectionRead])
def list_inspections(
    db: DbDep,
    task_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[QaInspection]:
    """Newest first."""
    stmt = select(QaInspection)
    if task_id is not None:
        stmt = stmt.where(QaInspection.task_id == task_id)
    stmt = stmt.order_by(desc(QaInspection.inspection_date), desc(QaInspection.id))
    return list(db.scalars(stmt.limit(limit).offset(offset)).all())


@router.get("/{inspection_id}", response_model=QaInspectionRead)
def get_inspection(inspection_id: int, db: DbDep) -> QaInspection:
    return _get_or_404(db, inspection_id)


@router.post("", response_model=QaInspectionRead, status_code=status.HTTP_201_CREATED)
def create_inspection(
    payload: QaInspectionCreate,
    db: DbDep,
    user: Annotated[User, Depends(require(Permission.QA))],
) -> QaInspection:
    """Record a QA/QC inspection. Only clearance tasks that are active or completed qualify."""
    task = db.get(Task, payload.task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Task {payload.task_id} not found")
    if task.task_type != TaskType.CLEARANCE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only clearance tasks can be inspected",
        )
    if task.status not in (TaskStatus.ACTIVE, TaskStatus.COMPLETED):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Task is '{task.status.value}'; only active or completed tasks can be inspected",
        )
    values = payload.model_dump()
    inspection = QaInspection(**values, inspector=user.username)
    db.add(inspection)
    db.flush()
    audit.record(
        db,
        "qa_inspection",
        inspection.id,
        "create",
        audit.created_values({**values, "inspector": user.username}),
        actor=user.username,
    )
    db.commit()
    db.refresh(inspection)
    return inspection


@router.delete("/{inspection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inspection(
    inspection_id: int,
    db: DbDep,
    user: Annotated[User, Depends(require(Permission.DELETE))],
) -> Response:
    inspection = _get_or_404(db, inspection_id)
    audit.record(
        db,
        "qa_inspection",
        inspection.id,
        "delete",
        {"task_id": [inspection.task_id, None]},
        actor=user.username,
    )
    db.delete(inspection)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
