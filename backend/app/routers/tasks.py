from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.auth import Permission, require
from app.config import get_settings
from app.db import get_db
from app.models import Hazard, Task, TaskStatus, TaskType, User
from app.schemas import TaskCreate, TaskRead, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])
DbDep = Annotated[Session, Depends(get_db)]


def _get_or_404(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found")
    return task


@router.get("", response_model=list[TaskRead])
def list_tasks(
    db: DbDep,
    hazard_id: int | None = None,
    status_: Annotated[TaskStatus | None, Query(alias="status")] = None,
    task_type: TaskType | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Task]:
    stmt = select(Task)
    if hazard_id is not None:
        stmt = stmt.where(Task.hazard_id == hazard_id)
    if status_:
        stmt = stmt.where(Task.status == status_)
    if task_type:
        stmt = stmt.where(Task.task_type == task_type)
    return list(db.scalars(stmt.order_by(Task.id).limit(limit).offset(offset)).all())


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: DbDep) -> Task:
    return _get_or_404(db, task_id)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate, db: DbDep, user: Annotated[User, Depends(require(Permission.WRITE))]
) -> Task:
    if db.get(Hazard, payload.hazard_id) is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Hazard {payload.hazard_id} not found"
        )
    values = payload.model_dump()
    task = Task(**values)
    db.add(task)
    db.flush()
    task.code = f"{get_settings().country_code}-TSK-{task.id:05d}"
    audit.record(
        db,
        "task",
        task.id,
        "create",
        audit.created_values({**values, "code": task.code}),
        actor=user.username,
    )
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: DbDep,
    user: Annotated[User, Depends(require(Permission.WRITE))],
) -> Task:
    task = _get_or_404(db, task_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is None and field in {"task_type", "status", "organisation"}:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{field} cannot be null"
            )
    start = changes.get("planned_start", task.planned_start)
    end = changes.get("planned_end", task.planned_end)
    if start and end and end < start:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="planned_end must not be before planned_start",
        )
    trail = audit.diff(task, changes)
    for field, value in changes.items():
        setattr(task, field, value)
    if trail:
        audit.record(db, "task", task.id, "update", trail, actor=user.username)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int, db: DbDep, user: Annotated[User, Depends(require(Permission.DELETE))]
) -> Response:
    task = _get_or_404(db, task_id)
    audit.record(db, "task", task.id, "delete", {"code": [task.code, None]}, actor=user.username)
    db.delete(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
