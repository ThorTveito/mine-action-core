"""Business rules for hazard lifecycle. Used by the API and by the import pipeline."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Hazard, HazardStatus, Task, TaskStatus, TaskType

S = HazardStatus

# Allowed hazard status transitions. `released` and `cancelled` are terminal in Tier 2.
ALLOWED_TRANSITIONS: dict[HazardStatus, frozenset[HazardStatus]] = {
    S.SUSPECTED: frozenset({S.CONFIRMED, S.CANCELLED}),
    S.CONFIRMED: frozenset({S.IN_CLEARANCE, S.CANCELLED}),
    S.IN_CLEARANCE: frozenset({S.RELEASED, S.CONFIRMED}),
    S.RELEASED: frozenset(),
    S.CANCELLED: frozenset(),
}

# A new hazard record can only enter the system as suspected or confirmed.
INITIAL_STATUSES = frozenset({S.SUSPECTED, S.CONFIRMED})

_OPEN_TASK_STATUSES = (TaskStatus.PLANNED, TaskStatus.ACTIVE, TaskStatus.SUSPENDED)


def check_initial_status(status: HazardStatus) -> str | None:
    if status in INITIAL_STATUSES:
        return None
    allowed = ", ".join(sorted(s.value for s in INITIAL_STATUSES))
    return f"A new hazard cannot start as '{status.value}' (allowed: {allowed})"


def check_transition(old: HazardStatus, new: HazardStatus) -> str | None:
    """Return an error message if old -> new is not allowed, else None."""
    if old == new or new in ALLOWED_TRANSITIONS[old]:
        return None
    allowed = ", ".join(sorted(s.value for s in ALLOWED_TRANSITIONS[old])) or "none (terminal)"
    return f"Cannot change status from '{old.value}' to '{new.value}' (allowed: {allowed})"


def check_release_preconditions(db: Session, hazard_id: int) -> str | None:
    """A hazard may be released only after clearance is finished and nothing is still open."""
    completed_clearance = db.scalar(
        select(func.count())
        .select_from(Task)
        .where(
            Task.hazard_id == hazard_id,
            Task.task_type == TaskType.CLEARANCE,
            Task.status == TaskStatus.COMPLETED,
        )
    )
    if not completed_clearance:
        return "Cannot release: the hazard has no completed clearance task"
    open_tasks = db.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.hazard_id == hazard_id, Task.status.in_(_OPEN_TASK_STATUSES))
    )
    if open_tasks:
        return f"Cannot release: {open_tasks} task(s) are still planned, active or suspended"
    return None


def check_status_change(db: Session, hazard: Hazard, new: HazardStatus) -> str | None:
    """Full check for moving an existing hazard to `new`."""
    if (msg := check_transition(hazard.status, new)) is not None:
        return msg
    if new == HazardStatus.RELEASED and hazard.status != HazardStatus.RELEASED:
        return check_release_preconditions(db, hazard.id)
    return None
