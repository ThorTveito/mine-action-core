from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.auth import Permission, require
from app.db import get_db
from app.models import RELEASE_METHOD_FOR_TASK, ClearanceRecord, Hazard, Task, User
from app.schemas import ClearanceRecordCreate, ClearanceRecordRead

router = APIRouter(prefix="/clearance-records", tags=["clearance"])
DbDep = Annotated[Session, Depends(get_db)]


def _get_or_404(db: Session, record_id: int) -> ClearanceRecord:
    record = db.get(ClearanceRecord, record_id)
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Clearance record {record_id} not found"
        )
    return record


@router.get("", response_model=list[ClearanceRecordRead])
def list_records(
    db: DbDep,
    task_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ClearanceRecord]:
    stmt = select(ClearanceRecord)
    if task_id is not None:
        stmt = stmt.where(ClearanceRecord.task_id == task_id)
    stmt = stmt.order_by(ClearanceRecord.record_date, ClearanceRecord.id)
    return list(db.scalars(stmt.limit(limit).offset(offset)).all())


@router.get("/{record_id}", response_model=ClearanceRecordRead)
def get_record(record_id: int, db: DbDep) -> ClearanceRecord:
    return _get_or_404(db, record_id)


@router.post("", response_model=ClearanceRecordRead, status_code=status.HTTP_201_CREATED)
def create_record(
    payload: ClearanceRecordCreate,
    db: DbDep,
    user: Annotated[User, Depends(require(Permission.WRITE))],
) -> ClearanceRecord:
    task = db.get(Task, payload.task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Task {payload.task_id} not found")
    expected = RELEASE_METHOD_FOR_TASK.get(task.task_type)
    if expected is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{task.task_type.value} tasks do not release land; record nothing here",
        )
    if payload.release_method is not None and payload.release_method != expected:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"A {task.task_type.value} task releases land as '{expected.value}', "
                f"not '{payload.release_method.value}'"
            ),
        )
    hazard = db.get(Hazard, task.hazard_id)
    assert hazard is not None
    released = db.scalar(
        select(func.coalesce(func.sum(ClearanceRecord.area_cleared_m2), 0.0))
        .join(Task, ClearanceRecord.task_id == Task.id)
        .where(Task.hazard_id == hazard.id)
    )
    if released + payload.area_cleared_m2 > hazard.area_m2 * 1.01:  # 1% for GPS rounding
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"This would release {released + payload.area_cleared_m2:,.0f} m2 in total, "
                f"more than {hazard.code}'s {hazard.area_m2:,.0f} m2"
            ),
        )
    values = payload.model_dump() | {"release_method": expected}
    record = ClearanceRecord(**values)
    db.add(record)
    db.flush()
    audit.record(
        db,
        "clearance_record",
        record.id,
        "create",
        audit.created_values(values),
        actor=user.username,
    )
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(
    record_id: int, db: DbDep, user: Annotated[User, Depends(require(Permission.DELETE))]
) -> Response:
    record = _get_or_404(db, record_id)
    audit.record(
        db,
        "clearance_record",
        record.id,
        "delete",
        {"task_id": [record.task_id, None]},
        actor=user.username,
    )
    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
