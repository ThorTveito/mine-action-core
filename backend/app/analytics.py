"""Aggregations shared by the public dashboard and the annual report.

Only aggregates leave this module: no names, no individual victims, no report text.
"""

from typing import Any

from sqlalchemy import case, extract, func, select
from sqlalchemy.orm import Session

from app.models import (
    Accident,
    ClearanceRecord,
    Hazard,
    HazardStatus,
    InspectionOutcome,
    QaInspection,
    ReleaseMethod,
    RiskEducationSession,
    Sex,
    Task,
    Victim,
    VictimOutcome,
)

OPEN = (HazardStatus.SUSPECTED, HazardStatus.CONFIRMED, HazardStatus.IN_CLEARANCE)
CHILD_AGE = 18


def _region(stmt: Any, region: str | None, column: Any = Hazard.region) -> Any:
    return stmt.where(column == region) if region else stmt


def _year(stmt: Any, year: int | None, column: Any) -> Any:
    return stmt.where(extract("year", column) == year) if year else stmt


def land_release(db: Session, region: str | None = None, year: int | None = None) -> dict[str, Any]:
    """Area released by method (cancelled by NTS, reduced by TS, cleared), and items, by year."""
    yr = extract("year", ClearanceRecord.record_date)
    stmt = (
        select(
            yr,
            ClearanceRecord.release_method,
            func.sum(ClearanceRecord.area_cleared_m2),
            func.sum(ClearanceRecord.items_found),
            func.sum(ClearanceRecord.items_destroyed),
        )
        .join(Task, ClearanceRecord.task_id == Task.id)
        .join(Hazard, Task.hazard_id == Hazard.id)
        .group_by(yr, ClearanceRecord.release_method)
        .order_by(yr)
    )
    stmt = _year(_region(stmt, region), year, ClearanceRecord.record_date)
    totals = {m.value: 0.0 for m in ReleaseMethod}
    by_year: dict[int, dict[str, Any]] = {}
    found = destroyed = 0
    for y, method, area, f, d in db.execute(stmt):
        row = by_year.setdefault(
            int(y), {"year": int(y), **{m.value: 0.0 for m in ReleaseMethod}, "items_destroyed": 0}
        )
        row[method.value] += float(area)
        row["items_destroyed"] += int(d)
        totals[method.value] += float(area)
        found += int(f)
        destroyed += int(d)
    return {
        "cancelled_m2": totals["cancelled"],
        "reduced_m2": totals["reduced"],
        "cleared_m2": totals["cleared"],
        "total_m2": sum(totals.values()),
        "items_found": found,
        "items_destroyed": destroyed,
        "by_year": list(by_year.values()),
    }


def outstanding_area(db: Session, region: str | None = None) -> float:
    """Open hazards' area minus what has already been released inside them."""
    released = (
        select(Task.hazard_id, func.sum(ClearanceRecord.area_cleared_m2).label("released"))
        .join(ClearanceRecord, ClearanceRecord.task_id == Task.id)
        .group_by(Task.hazard_id)
        .subquery()
    )
    left = func.greatest(Hazard.area_m2 - func.coalesce(released.c.released, 0.0), 0.0)
    stmt = (
        select(func.coalesce(func.sum(left), 0.0))
        .select_from(Hazard)
        .outerjoin(released, released.c.hazard_id == Hazard.id)
        .where(Hazard.status.in_(OPEN))
    )
    return float(db.scalar(_region(stmt, region)) or 0.0)


def casualties(db: Session, region: str | None = None, year: int | None = None) -> dict[str, Any]:
    """Accidents and casualties, disaggregated by sex and age group (SADD)."""
    acc_stmt = _year(
        _region(select(func.count()).select_from(Accident), region, Accident.region),
        year,
        Accident.occurred_on,
    )
    accidents = int(db.scalar(acc_stmt) or 0)

    age_group = case(
        (Victim.age.is_(None), "unknown"), (Victim.age < CHILD_AGE, "child"), else_="adult"
    )
    stmt = (
        select(Victim.sex, age_group, Victim.outcome, Victim.is_deminer, func.count())
        .join(Accident, Victim.accident_id == Accident.id)
        .group_by(Victim.sex, age_group, Victim.outcome, Victim.is_deminer)
    )
    stmt = _year(_region(stmt, region, Accident.region), year, Accident.occurred_on)
    by_sex = {s.value: 0 for s in Sex}
    by_age = {"child": 0, "adult": 0, "unknown": 0}
    # The SADD grid: sex x age group, as reported to donors and treaty bodies.
    grid = {f"{s.value}_{a}": 0 for s in Sex for a in by_age}
    killed = injured = deminers = 0
    for sex, group, outcome, deminer, n in db.execute(stmt):
        by_sex[sex.value] += n
        by_age[group] += n
        grid[f"{sex.value}_{group}"] += n
        if outcome == VictimOutcome.KILLED:
            killed += n
        else:
            injured += n
        if deminer:
            deminers += n

    yr = extract("year", Accident.occurred_on)
    trend = (
        select(
            yr,
            func.count(func.distinct(Accident.id)),
            func.count(Victim.id).filter(Victim.outcome == VictimOutcome.KILLED),
            func.count(Victim.id).filter(Victim.outcome == VictimOutcome.INJURED),
        )
        .outerjoin(Victim, Victim.accident_id == Accident.id)
        .group_by(yr)
        .order_by(yr)
    )
    trend = _region(trend, region, Accident.region)
    by_activity = {
        a.value: n
        for a, n in db.execute(
            _year(
                _region(
                    select(Accident.activity, func.count()).group_by(Accident.activity),
                    region,
                    Accident.region,
                ),
                year,
                Accident.occurred_on,
            )
        )
    }
    return {
        "accidents": accidents,
        "casualties": killed + injured,
        "killed": killed,
        "injured": injured,
        "deminers": deminers,
        "by_sex": by_sex,
        "by_age_group": by_age,
        "sadd": grid,
        "by_activity": by_activity,
        "by_year": [
            {"year": int(y), "accidents": int(a), "killed": int(k), "injured": int(i)}
            for y, a, k, i in db.execute(trend)
        ],
    }


def risk_education(
    db: Session, region: str | None = None, year: int | None = None
) -> dict[str, Any]:
    s = RiskEducationSession
    stmt = select(
        func.count(),
        func.coalesce(func.sum(s.girls), 0),
        func.coalesce(func.sum(s.boys), 0),
        func.coalesce(func.sum(s.women), 0),
        func.coalesce(func.sum(s.men), 0),
    )
    stmt = _year(_region(stmt.select_from(s), region, s.region), year, s.held_on)
    sessions, girls, boys, women, men = db.execute(stmt).one()
    yr = extract("year", s.held_on)
    trend = _region(
        select(yr, func.count(), func.sum(s.girls + s.boys + s.women + s.men))
        .group_by(yr)
        .order_by(yr),
        region,
        s.region,
    )
    return {
        "sessions": int(sessions),
        "girls": int(girls),
        "boys": int(boys),
        "women": int(women),
        "men": int(men),
        "total": int(girls + boys + women + men),
        "by_year": [
            {"year": int(y), "sessions": int(n), "people": int(p)} for y, n, p in db.execute(trend)
        ],
    }


def qa_summary(db: Session, region: str | None = None, year: int | None = None) -> dict[str, Any]:
    stmt = (
        select(
            QaInspection.outcome,
            func.count(),
            func.coalesce(func.sum(QaInspection.residual_items_found), 0),
        )
        .join(Task, QaInspection.task_id == Task.id)
        .join(Hazard, Task.hazard_id == Hazard.id)
        .group_by(QaInspection.outcome)
    )
    stmt = _year(_region(stmt, region), year, QaInspection.inspection_date)
    passed = failed = residual = 0
    for outcome, n, res in db.execute(stmt):
        if outcome == InspectionOutcome.PASS:
            passed = n
        else:
            failed = n
        residual += int(res)
    total = passed + failed
    return {
        "inspections": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(100 * passed / total, 1) if total else None,
        "residual_items": residual,
    }
