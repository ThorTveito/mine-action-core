from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ClearanceRecord, Hazard, HazardStatus, Task, TaskStatus
from app.schemas import Dashboard, MonthlyClearance, RegionProgress, Stats

router = APIRouter(tags=["stats"])
DbDep = Annotated[Session, Depends(get_db)]


@router.get("/stats", response_model=Stats)
def get_stats(db: DbDep) -> Stats:
    by_status = {s.value: 0 for s in HazardStatus}
    for status_, count in db.execute(select(Hazard.status, func.count()).group_by(Hazard.status)):
        by_status[status_.value] = count

    total_area = db.scalar(select(func.coalesce(func.sum(Hazard.area_m2), 0.0))) or 0.0
    released_area = (
        db.scalar(
            select(func.coalesce(func.sum(Hazard.area_m2), 0.0)).where(
                Hazard.status == HazardStatus.RELEASED
            )
        )
        or 0.0
    )
    cleared_area, destroyed = db.execute(
        select(
            func.coalesce(func.sum(ClearanceRecord.area_cleared_m2), 0.0),
            func.coalesce(func.sum(ClearanceRecord.items_destroyed), 0),
        )
    ).one()
    open_tasks = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.status.in_([TaskStatus.PLANNED, TaskStatus.ACTIVE, TaskStatus.SUSPENDED]))
        )
        or 0
    )

    return Stats(
        hazard_count=sum(by_status.values()),
        hazards_by_status=by_status,
        total_area_m2=float(total_area),
        released_area_m2=float(released_area),
        cleared_area_m2=float(cleared_area),
        open_task_count=int(open_tasks),
        items_destroyed=int(destroyed),
    )


_REMAINING = (HazardStatus.SUSPECTED, HazardStatus.CONFIRMED, HazardStatus.IN_CLEARANCE)


@router.get("/dashboard", response_model=Dashboard)
def get_dashboard(db: DbDep) -> Dashboard:
    """Progress figures for the dashboard. Areas are geodesic square metres."""
    area_by_status = {s.value: 0.0 for s in HazardStatus}
    for status_, area in db.execute(
        select(Hazard.status, func.coalesce(func.sum(Hazard.area_m2), 0.0)).group_by(Hazard.status)
    ):
        area_by_status[status_.value] = float(area)

    remaining = sum(area_by_status[s.value] for s in _REMAINING)
    released = area_by_status[HazardStatus.RELEASED.value]
    cancelled = area_by_status[HazardStatus.CANCELLED.value]
    contaminated = remaining + released
    release_percent = round(100 * released / contaminated, 1) if contaminated else 0.0

    tasks_by_status = {s.value: 0 for s in TaskStatus}
    for status_, count in db.execute(select(Task.status, func.count()).group_by(Task.status)):
        tasks_by_status[status_.value] = count

    cleared_by_region = {
        region: float(area)
        for region, area in db.execute(
            select(Hazard.region, func.sum(ClearanceRecord.area_cleared_m2))
            .join(Task, Task.hazard_id == Hazard.id)
            .join(ClearanceRecord, ClearanceRecord.task_id == Task.id)
            .group_by(Hazard.region)
        )
    }
    by_region = []
    for region, count in db.execute(
        select(Hazard.region, func.count()).group_by(Hazard.region).order_by(Hazard.region)
    ):
        areas = {s.value: 0.0 for s in HazardStatus}
        for status_, area in db.execute(
            select(Hazard.status, func.sum(Hazard.area_m2))
            .where(Hazard.region == region)
            .group_by(Hazard.status)
        ):
            areas[status_.value] = float(area)
        region_remaining = sum(areas[s.value] for s in _REMAINING)
        region_released = areas[HazardStatus.RELEASED.value]
        by_region.append(
            RegionProgress(
                region=region,
                hazard_count=count,
                total_area_m2=region_remaining + region_released,
                remaining_area_m2=region_remaining,
                released_area_m2=region_released,
                cleared_area_m2=cleared_by_region.get(region, 0.0),
            )
        )

    month = func.to_char(ClearanceRecord.record_date, "YYYY-MM")
    monthly = [
        MonthlyClearance(month=m, cleared_area_m2=float(a), items_destroyed=int(d))
        for m, a, d in db.execute(
            select(
                month,
                func.sum(ClearanceRecord.area_cleared_m2),
                func.sum(ClearanceRecord.items_destroyed),
            )
            .group_by(month)
            .order_by(month)
        )
    ]

    return Dashboard(
        contaminated_area_m2=contaminated,
        remaining_area_m2=remaining,
        released_area_m2=released,
        cancelled_area_m2=cancelled,
        release_percent=release_percent,
        area_by_status=area_by_status,
        tasks_by_status=tasks_by_status,
        by_region=by_region,
        monthly_clearance=monthly,
    )
