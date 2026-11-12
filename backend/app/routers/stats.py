from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import topology
from app.db import get_db
from app.models import (
    AuditLog,
    ClearanceRecord,
    FieldReport,
    FindingType,
    Hazard,
    HazardStatus,
    InspectionOutcome,
    QaInspection,
    ReportStatus,
    Task,
    TaskStatus,
    TaskType,
)
from app.schemas import (
    ActivityItem,
    ClassBreakdown,
    Dashboard,
    DataQuality,
    FieldReportSummary,
    MonthlyClearance,
    OrganisationStats,
    QaSummary,
    RegionProgress,
    Stats,
)

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
_OPEN_TASKS = (TaskStatus.PLANNED, TaskStatus.ACTIVE, TaskStatus.SUSPENDED)
_PUBLIC_ACTIVITY = ("hazard", "task", "clearance_record", "qa_inspection")


def _in_region(stmt: Any, region: str | None) -> Any:
    return stmt.where(Hazard.region == region) if region else stmt


@router.get("/dashboard", response_model=Dashboard)
def get_dashboard(db: DbDep, region: str | None = None) -> Dashboard:
    """Public progress figures. Areas are geodesic square metres.

    `region` narrows the hazard, task, clearance and QA figures; field reports, data
    quality and recent activity always cover all regions. Only aggregates are returned:
    no field report details and no user names.
    """
    regions = list(db.scalars(select(Hazard.region).distinct().order_by(Hazard.region)))
    if region is not None and region not in regions:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Unknown region '{region}'")

    # --- hazards
    area_by_status = {s.value: 0.0 for s in HazardStatus}
    count_by_status = {s.value: 0 for s in HazardStatus}
    for st, area, n in db.execute(
        _in_region(
            select(Hazard.status, func.coalesce(func.sum(Hazard.area_m2), 0.0), func.count()),
            region,
        ).group_by(Hazard.status)
    ):
        area_by_status[st.value] = float(area)
        count_by_status[st.value] = n
    remaining = sum(area_by_status[s.value] for s in _REMAINING)
    released = area_by_status[HazardStatus.RELEASED.value]
    cancelled = area_by_status[HazardStatus.CANCELLED.value]
    contaminated = remaining + released

    by_class = [
        ClassBreakdown(hazard_class=c.value, hazard_count=n, area_m2=float(a))
        for c, n, a in db.execute(
            _in_region(
                select(Hazard.hazard_class, func.count(), func.sum(Hazard.area_m2)).where(
                    Hazard.status != HazardStatus.CANCELLED
                ),
                region,
            )
            .group_by(Hazard.hazard_class)
            .order_by(func.sum(Hazard.area_m2).desc())
        )
    ]

    # --- tasks
    tasks_by_status = {s.value: 0 for s in TaskStatus}
    for st, n in db.execute(
        _in_region(select(Task.status, func.count()).join(Hazard), region).group_by(Task.status)
    ):
        tasks_by_status[st.value] = n
    tasks_by_type = {t.value: 0 for t in TaskType}
    for tt, n in db.execute(
        _in_region(select(Task.task_type, func.count()).join(Hazard), region).group_by(
            Task.task_type
        )
    ):
        tasks_by_type[tt.value] = n

    # --- regions
    cleared_by_region = {
        r: float(a)
        for r, a in db.execute(
            select(Hazard.region, func.sum(ClearanceRecord.area_cleared_m2))
            .join(Task, Task.hazard_id == Hazard.id)
            .join(ClearanceRecord, ClearanceRecord.task_id == Task.id)
            .group_by(Hazard.region)
        )
    }
    region_areas: dict[str, dict[str, float]] = {}
    region_counts: dict[str, int] = {}
    for r, st, area, n in db.execute(
        select(Hazard.region, Hazard.status, func.sum(Hazard.area_m2), func.count()).group_by(
            Hazard.region, Hazard.status
        )
    ):
        region_areas.setdefault(r, {})[st.value] = float(area)
        region_counts[r] = region_counts.get(r, 0) + n
    by_region = []
    for r in regions:
        if region and r != region:
            continue
        areas = region_areas.get(r, {})
        r_remaining = sum(areas.get(s.value, 0.0) for s in _REMAINING)
        r_released = areas.get(HazardStatus.RELEASED.value, 0.0)
        by_region.append(
            RegionProgress(
                region=r,
                hazard_count=region_counts.get(r, 0),
                total_area_m2=r_remaining + r_released,
                remaining_area_m2=r_remaining,
                released_area_m2=r_released,
                cleared_area_m2=cleared_by_region.get(r, 0.0),
            )
        )

    # --- clearance over time
    month = func.to_char(ClearanceRecord.record_date, "YYYY-MM")
    monthly = [
        MonthlyClearance(
            month=m, cleared_area_m2=float(a), items_destroyed=int(d), items_found=int(f)
        )
        for m, a, d, f in db.execute(
            _in_region(
                select(
                    month,
                    func.sum(ClearanceRecord.area_cleared_m2),
                    func.sum(ClearanceRecord.items_destroyed),
                    func.sum(ClearanceRecord.items_found),
                )
                .join(Task, ClearanceRecord.task_id == Task.id)
                .join(Hazard, Task.hazard_id == Hazard.id),
                region,
            )
            .group_by(month)
            .order_by(month)
        )
    ]

    # --- organisations
    orgs: dict[str, OrganisationStats] = {}
    for org, st, n in db.execute(
        _in_region(select(Task.organisation, Task.status, func.count()).join(Hazard), region)
        .group_by(Task.organisation, Task.status)
    ):
        o = orgs.setdefault(
            org,
            OrganisationStats(
                organisation=org, tasks=0, active_tasks=0, completed_tasks=0,
                cleared_area_m2=0.0, items_destroyed=0,
            ),
        )  # fmt: skip
        o.tasks += n
        if st in _OPEN_TASKS:
            o.active_tasks += n
        if st == TaskStatus.COMPLETED:
            o.completed_tasks += n
    for org, area, destroyed in db.execute(
        _in_region(
            select(
                Task.organisation,
                func.sum(ClearanceRecord.area_cleared_m2),
                func.sum(ClearanceRecord.items_destroyed),
            )
            .join(ClearanceRecord, ClearanceRecord.task_id == Task.id)
            .join(Hazard, Task.hazard_id == Hazard.id),
            region,
        ).group_by(Task.organisation)
    ):
        if org in orgs:
            orgs[org].cleared_area_m2 = float(area)
            orgs[org].items_destroyed = int(destroyed)

    # --- QA
    passed = failed = residual = 0
    for outcome, n, res in db.execute(
        _in_region(
            select(
                QaInspection.outcome,
                func.count(),
                func.coalesce(func.sum(QaInspection.residual_items_found), 0),
            )
            .join(Task, QaInspection.task_id == Task.id)
            .join(Hazard, Task.hazard_id == Hazard.id),
            region,
        ).group_by(QaInspection.outcome)
    ):
        if outcome == InspectionOutcome.PASS:
            passed = n
        else:
            failed = n
        residual += int(res)
    inspections = passed + failed
    qa = QaSummary(
        inspections=inspections,
        passed=passed,
        failed=failed,
        pass_rate=round(100 * passed / inspections, 1) if inspections else None,
        residual_items=residual,
    )

    return Dashboard(
        region=region,
        regions=regions,
        hazard_count=sum(count_by_status.values()),
        open_hazard_count=sum(count_by_status[s.value] for s in _REMAINING),
        contaminated_area_m2=contaminated,
        remaining_area_m2=remaining,
        released_area_m2=released,
        cancelled_area_m2=cancelled,
        release_percent=round(100 * released / contaminated, 1) if contaminated else 0.0,
        items_found=sum(m.items_found for m in monthly),
        items_destroyed=sum(m.items_destroyed for m in monthly),
        area_by_status=area_by_status,
        hazards_by_status=count_by_status,
        hazards_by_class=by_class,
        tasks_by_status=tasks_by_status,
        tasks_by_type=tasks_by_type,
        by_region=by_region,
        monthly_clearance=monthly,
        organisations=sorted(orgs.values(), key=lambda o: -o.cleared_area_m2),
        qa=qa,
        field_reports=_field_report_summary(db),
        data_quality=_data_quality(db),
        recent_activity=_recent_activity(db),
    )


def _field_report_summary(db: Session) -> FieldReportSummary:
    by_status = {s.value: 0 for s in ReportStatus}
    for st, n in db.execute(
        select(FieldReport.status, func.count()).group_by(FieldReport.status)
    ):
        by_status[st.value] = n
    by_type = {t.value: 0 for t in FindingType}
    for ft, n in db.execute(
        select(FieldReport.finding_type, func.count()).group_by(FieldReport.finding_type)
    ):
        by_type[ft.value] = n
    hours = func.extract("epoch", FieldReport.reviewed_at - FieldReport.received_at) / 3600
    median = db.scalar(
        select(func.percentile_cont(0.5).within_group(hours)).where(
            FieldReport.reviewed_at.is_not(None)
        )
    )
    return FieldReportSummary(
        total=sum(by_status.values()),
        by_status=by_status,
        by_finding_type=by_type,
        median_review_hours=round(float(median), 1) if median is not None else None,
    )


def _data_quality(db: Session) -> DataQuality:
    _, issues = topology.check(db)
    by_rule: dict[str, int] = {}
    for i in issues:
        by_rule[i.rule] = by_rule.get(i.rule, 0) + 1
    return DataQuality(
        errors=sum(1 for i in issues if i.severity == "error"),
        warnings=sum(1 for i in issues if i.severity == "warning"),
        by_rule=by_rule,
    )


def _source_label(source: str) -> str:
    if source.startswith("import:"):
        return "import"
    if source.startswith("field_report:"):
        return "field report"
    return source


def _recent_activity(db: Session, limit: int = 12) -> list[ActivityItem]:
    """Latest changes to public data, described in words. No user names."""
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type.in_(_PUBLIC_ACTIVITY))
        .order_by(AuditLog.id.desc())
        .limit(limit)
    ).all()
    hazard_ids = {r.entity_id for r in rows if r.entity_type == "hazard"}
    task_ids = {r.entity_id for r in rows if r.entity_type == "task"}
    hazard_code = dict(db.execute(select(Hazard.id, Hazard.code).where(Hazard.id.in_(hazard_ids))).all())
    task_code = dict(db.execute(select(Task.id, Task.code).where(Task.id.in_(task_ids))).all())

    def words(v: object) -> object:
        return v.replace("_", " ") if isinstance(v, str) else v

    def describe(r: AuditLog) -> str:
        ch = r.changes or {}
        new = {k: words(v[1]) for k, v in ch.items() if isinstance(v, list) and len(v) == 2}
        old = {k: words(v[0]) for k, v in ch.items() if isinstance(v, list) and len(v) == 2}
        if r.entity_type == "hazard":
            code = hazard_code.get(r.entity_id) or ch.get("code", [None, None])[1] or "hazard"
            if r.action == "create":
                return f"{code} registered ({new.get('status', 'suspected')})"
            if r.action == "delete":
                return f"{code} deleted"
            if "status" in ch:
                return f"{code}: {old['status']} → {new['status']}"
            return f"{code} updated ({', '.join(sorted(ch))})"
        if r.entity_type == "task":
            code = task_code.get(r.entity_id) or ch.get("code", [None, None])[1] or "task"
            if r.action == "create":
                return f"{code}: {new.get('task_type', 'task')} task planned"
            if "status" in ch:
                return f"{code}: {old['status']} → {new['status']}"
            return f"{code} {r.action}d"
        if r.entity_type == "clearance_record":
            area = new.get("area_cleared_m2")
            return f"Clearance record: {area:,.0f} m² cleared" if area else "Clearance record added"
        outcome = new.get("outcome")
        return f"QA inspection: {outcome}" if outcome else "QA inspection recorded"

    return [
        ActivityItem(
            at=r.created_at,
            entity_type=r.entity_type,
            action=r.action,
            source=_source_label(r.source),
            summary=describe(r),
        )
        for r in rows
    ]
