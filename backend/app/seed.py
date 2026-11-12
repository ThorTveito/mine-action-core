"""Deterministic synthetic data for the fictional country of Karvonia.

Run with: python -m app.seed   (destructive: wipes hazards, tasks, records)

Nothing here is real. Coordinates are an arbitrary patch of land chosen only so
the map has something to show; region and organisation names are invented.
"""

import math
import random
from datetime import UTC, date, datetime, timedelta

from geoalchemy2.shape import from_shape, to_shape
from shapely.affinity import translate
from shapely.geometry import Point, Polygon, box
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import audit, bootstrap, geo
from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    ClearanceRecord,
    FieldReport,
    FindingType,
    Hazard,
    HazardClass,
    HazardStatus,
    HazardType,
    InspectionOutcome,
    InspectionType,
    ItemCategory,
    QaInspection,
    ReportSource,
    ReportStatus,
    Task,
    TaskStatus,
    TaskType,
)

# The layout below was designed around (18.0E, 15.0N). SHIFT_* moves everything onto
# mountainous terrain (around 8.2E, 61.5N) so the 3D terrain view has real relief to show.
# Karvonia is fictional; only the ground under it is real.
SHIFT_LON, SHIFT_LAT = -9.8, 46.5
_BASE_REGIONS = {  # name -> (lon, lat) centre before the shift
    "Northern Marches": (18.20, 15.55),
    "Eastern Uplands": (18.75, 15.10),
    "Central Basin": (18.15, 15.05),
    "Southern Plains": (18.10, 14.55),
    "River Delta": (17.60, 14.95),
    "Western Ridge": (17.50, 15.45),
}
REGIONS = {k: (lon + SHIFT_LON, lat + SHIFT_LAT) for k, (lon, lat) in _BASE_REGIONS.items()}
ORGANISATIONS = ["Karvonian Demining Authority", "Northgate Clearance", "Delta Mine Action NGO"]
TEAMS = ["Team Alpha", "Team Bravo", "Team Charlie", "Team Delta", "Team Echo"]
NAME_PREFIX = ["Old", "Upper", "Lower", "Ridge", "Mill", "Church", "Bridge", "Quarry", "Pasture"]
NAME_SUFFIX = ["Road", "Field", "Crossing", "Ford", "Orchard", "Hill", "Village Edge", "Pass"]

# Weighted so the map shows a realistic mix of lifecycle stages.
STATUS_WEIGHTS = [
    (HazardStatus.SUSPECTED, 25),
    (HazardStatus.CONFIRMED, 25),
    (HazardStatus.IN_CLEARANCE, 15),
    (HazardStatus.RELEASED, 28),
    (HazardStatus.CANCELLED, 7),
]
HAZARD_COUNT = 60


def _blob(rng: random.Random, lon: float, lat: float, radius_m: float) -> Polygon:
    """A lumpy, always-valid polygon around a centre point."""
    n = rng.randint(7, 11)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(lat))
    points = []
    for i in range(n):
        angle = 2 * math.pi * i / n
        r = radius_m * rng.uniform(0.6, 1.1)
        points.append((lon + r * math.cos(angle) / m_per_deg_lon, lat + r * math.sin(angle) / m_per_deg_lat))
    return Polygon(points)


def _wipe(db: Session) -> None:
    db.execute(text("TRUNCATE audit_log, field_reports, qa_inspections, clearance_records, tasks, hazards RESTART IDENTITY CASCADE"))


def _add_task(
    db: Session, hazard: Hazard, task_type: TaskType, status: TaskStatus, rng: random.Random
) -> Task:
    start = date(2025, 1, 1) + timedelta(days=rng.randint(0, 600))
    task = Task(
        hazard_id=hazard.id,
        task_type=task_type,
        status=status,
        organisation=rng.choice(ORGANISATIONS),
        planned_start=start,
        planned_end=start + timedelta(days=rng.randint(14, 120)),
        description=f"{task_type.value.capitalize()} of {hazard.name}",
    )
    db.add(task)
    db.flush()
    task.code = f"{get_settings().country_code}-TSK-{task.id:05d}"
    return task


def _add_records(
    db: Session, task: Task, total_area: float, fraction: float, rng: random.Random
) -> date:
    """Split `fraction` of `total_area` into dated clearance records; returns the last day."""
    remaining = total_area * fraction
    day = task.planned_start or date(2025, 1, 1)
    last = day
    while remaining > 1:
        chunk = min(remaining, total_area / rng.randint(6, 14))
        found = rng.randint(0, 6)
        db.add(
            ClearanceRecord(
                task_id=task.id,
                record_date=day,
                area_cleared_m2=round(chunk, 1),
                items_found=found,
                items_destroyed=found if rng.random() < 0.9 else max(found - 1, 0),
                team=rng.choice(TEAMS),
                notes=None,
            )
        )
        remaining -= chunk
        last = day
        day += timedelta(days=rng.randint(1, 4))
    return last


def _add_qa(
    db: Session,
    task: Task,
    day: date,
    outcome: InspectionOutcome,
    rng: random.Random,
    area_m2: float,
) -> None:
    failed = outcome == InspectionOutcome.FAIL
    inspection = QaInspection(
        task_id=task.id,
        inspection_type=InspectionType.QA,
        inspection_date=day,
        inspector="qa",
        sample_area_m2=round(area_m2 * 0.1, 1),
        residual_items_found=rng.randint(1, 2) if failed else 0,
        outcome=outcome,
        notes="Residual item found in sample; re-clearance required." if failed else None,
    )
    db.add(inspection)
    db.flush()
    audit.record(
        db,
        "qa_inspection",
        inspection.id,
        "create",
        audit.created_values(
            {"task_id": task.id, "outcome": outcome, "inspector": "qa", "inspection_date": day}
        ),
        source="seed",
        actor="qa",
    )


def _add_lifecycle(
    db: Session,
    hazard: Hazard,
    status: HazardStatus,
    rng: random.Random,
    qa_rng: random.Random,
) -> None:
    """Tasks, records and QA that are consistent with the hazard's status."""
    match status:
        case HazardStatus.SUSPECTED:
            if rng.random() < 0.5:
                _add_task(db, hazard, TaskType.SURVEY, TaskStatus.PLANNED, rng)
        case HazardStatus.CONFIRMED:
            _add_task(db, hazard, TaskType.CLEARANCE, TaskStatus.PLANNED, rng)
        case HazardStatus.IN_CLEARANCE:
            task = _add_task(db, hazard, TaskType.CLEARANCE, TaskStatus.ACTIVE, rng)
            last = _add_records(db, task, hazard.area_m2, rng.uniform(0.15, 0.8), rng)
            if qa_rng.random() < 0.3:  # a sampling inspection that found something
                _add_qa(db, task, last, InspectionOutcome.FAIL, qa_rng, hazard.area_m2)
        case HazardStatus.RELEASED:
            task = _add_task(db, hazard, TaskType.CLEARANCE, TaskStatus.COMPLETED, rng)
            last = _add_records(db, task, hazard.area_m2, 1.0, rng)
            _add_task(db, hazard, TaskType.VERIFICATION, TaskStatus.COMPLETED, rng)
            _add_qa(db, task, last + timedelta(days=2), InspectionOutcome.PASS, qa_rng, hazard.area_m2)
        case HazardStatus.CANCELLED:
            _add_task(db, hazard, TaskType.SURVEY, TaskStatus.COMPLETED, rng)


def _create_hazard(
    db: Session,
    name: str,
    hazard_class: HazardClass,
    status: HazardStatus,
    region: str,
    geom: Polygon,
    description: str = "Synthetic hazard record for demonstration.",
) -> Hazard:
    valid = geo.parse_polygonal_geojson(geom.__geo_interface__)
    hazard = Hazard(
        name=name,
        hazard_type=HazardType.SHA if status == HazardStatus.SUSPECTED else HazardType.CHA,
        hazard_class=hazard_class,
        status=status,
        region=region,
        description=description,
        geom=geo.to_db_geometry(valid),
        area_m2=geo.area_m2(db, valid),
    )
    db.add(hazard)
    db.flush()
    hazard.code = f"{get_settings().country_code}-HAZ-{hazard.id:05d}"
    audit.record(
        db,
        "hazard",
        hazard.id,
        "create",
        audit.created_values({"code": hazard.code, "status": status, "area_m2": hazard.area_m2}),
        source="seed",
    )
    return hazard


def _topology_scenarios(db: Session, rng: random.Random, qa_rng: random.Random) -> None:
    """Deliberate spatial-check cases in an empty corner of Southern Plains (docs/topology.md)."""
    region, s = "Southern Plains", HazardStatus
    needle = Polygon(
        [
            (18.530, 14.800), (18.534, 14.800), (18.534, 14.804), (18.5321, 14.804),
            (18.53205, 14.810), (18.5319, 14.804), (18.530, 14.804), (18.530, 14.800),
        ]
    )  # fmt: skip
    cases: list[tuple[str, HazardClass, HazardStatus, Polygon, str]] = [
        ("Adjoining Field A", HazardClass.ANTI_PERSONNEL, s.CONFIRMED, box(18.450, 14.800, 18.454, 14.804), "Cluster: shares edges with B and C"),
        ("Adjoining Field B", HazardClass.ANTI_PERSONNEL, s.CONFIRMED, box(18.454, 14.800, 18.458, 14.804), "Cluster: shares an edge with A"),
        ("Adjoining Field C", HazardClass.MIXED, s.IN_CLEARANCE, box(18.450, 14.804, 18.454, 14.808), "Cluster: shares an edge with A"),
        ("Undershoot West", HazardClass.UXO, s.CONFIRMED, box(18.470, 14.800, 18.474, 14.804), "Near miss: about 1 m from Undershoot East"),
        ("Undershoot East", HazardClass.UXO, s.CONFIRMED, box(18.47401, 14.800, 18.47801, 14.804), "Near miss: about 1 m from Undershoot West"),
        ("Overlap Orchard North", HazardClass.ANTI_VEHICLE, s.SUSPECTED, box(18.490, 14.800, 18.494, 14.804), "Overlap error with Overlap Orchard South"),
        ("Overlap Orchard South", HazardClass.ANTI_VEHICLE, s.CONFIRMED, box(18.492, 14.802, 18.496, 14.806), "Overlap error with Overlap Orchard North"),
        ("Released Meadow", HazardClass.ANTI_PERSONNEL, s.RELEASED, box(18.500, 14.800, 18.504, 14.804), "Release conflict with Re-reported Meadow"),
        ("Re-reported Meadow", HazardClass.ANTI_PERSONNEL, s.CONFIRMED, box(18.502, 14.800, 18.506, 14.804), "Overlaps a released hazard"),
        ("Boundary Strip", HazardClass.MIXED, s.CONFIRMED, box(18.520, 14.800, 18.52004, 14.810), "Sliver: a thin strip"),
        ("Needle Pasture", HazardClass.CLUSTER_MUNITION, s.SUSPECTED, needle, "Spike: a needle-like vertex"),
        ("Marker Stone", HazardClass.UXO, s.SUSPECTED, box(18.540, 14.800, 18.54002, 14.80002), "Tiny area: probably a digitising mistake"),
    ]  # fmt: skip
    for name, hazard_class, status, geom, description in cases:
        geom = translate(geom, SHIFT_LON, SHIFT_LAT)
        hazard = _create_hazard(db, name, hazard_class, status, region, geom, description)
        _add_lifecycle(db, hazard, status, rng, qa_rng)

def _add_report(
    db: Session,
    point: Point,
    day: int,
    finding_type: FindingType,
    description: str,
    item: ItemCategory | None = None,
    quantity: int | None = None,
    source: ReportSource = ReportSource.DIRECT_OBSERVATION,
    status: ReportStatus = ReportStatus.SUBMITTED,
    hazard: Hazard | None = None,
    note: str | None = None,
) -> FieldReport:
    observed = datetime(2026, 10, day, 9, 30, tzinfo=UTC)
    report = FieldReport(
        client_id=f"seed-{day:02d}-{finding_type.value}",
        reported_by="surveyor",
        observed_at=observed,
        finding_type=finding_type,
        item_category=item,
        quantity=quantity,
        source=source,
        description=description,
        location=from_shape(point, srid=geo.SRID),
        gps_accuracy_m=6.0,
        status=status,
        hazard_id=hazard.id if hazard else None,
        reviewed_by="editor" if status != ReportStatus.SUBMITTED else None,
        reviewed_at=observed + timedelta(days=1) if status != ReportStatus.SUBMITTED else None,
        review_note=note,
    )
    db.add(report)
    db.flush()
    report.code = f"{get_settings().country_code}-FR-{report.id:05d}"
    audit.record(
        db,
        "field_report",
        report.id,
        "create",
        audit.created_values({"code": report.code, "finding_type": finding_type}),
        source="seed",
        actor="surveyor",
    )
    return report


def _field_reports(db: Session) -> None:
    """A small inbox that exercises every triage path (see docs/field-reports.md)."""
    hazards = db.scalars(select(Hazard).order_by(Hazard.id)).all()
    released = next(h for h in hazards if h.status == HazardStatus.RELEASED)
    confirmed = [h for h in hazards if h.status == HazardStatus.CONFIRMED]
    active = next(h for h in hazards if h.status == HazardStatus.IN_CLEARANCE)

    def inside(h: Hazard) -> Point:
        return to_shape(h.geom).representative_point()

    def east_of(h: Hazard, metres: float) -> Point:
        shape = to_shape(h.geom)
        c = shape.representative_point()
        lon = shape.bounds[2] + metres / (111_320 * math.cos(math.radians(c.y)))
        return Point(lon, c.y)

    c_lon, c_lat = REGIONS["Central Basin"]
    near = east_of(confirmed[0], 80)
    _add_report(
        db, inside(released), 3, FindingType.ITEM_FOUND,
        "Corroded mortar round exposed after heavy rain, inside the fenced released field.",
        ItemCategory.UXO, 1,
    )  # fmt: skip
    _add_report(
        db, near, 5, FindingType.ITEM_FOUND,
        "Two anti-personnel mines visible on the footpath east of the marked area.",
        ItemCategory.AP_MINE, 2,
    )  # fmt: skip
    _add_report(
        db, Point(c_lon + 0.2, c_lat + 0.01), 8, FindingType.SUSPECTED_AREA,
        "Shepherd reports animals killed by explosions on the upper pasture in 2019.",
        source=ReportSource.LOCAL_INFORMANT,
    )  # fmt: skip
    _add_report(
        db, east_of(active, 30), 9, FindingType.ACCIDENT,
        "Tractor damaged by a blast at the field edge; driver unhurt. Reported by police.",
        ItemCategory.AV_MINE, 1, ReportSource.AUTHORITY,
    )  # fmt: skip
    _add_report(
        db, inside(confirmed[1]), 2, FindingType.ITEM_FOUND,
        "Fragment of a mine casing at the edge of the field.",
        ItemCategory.AP_MINE, 1, status=ReportStatus.ACCEPTED, hazard=confirmed[1],
        note="Inside the known hazard; linked.",
    )  # fmt: skip
    _add_report(
        db, near, 6, FindingType.ITEM_FOUND,
        "Same footpath, two mines (second visit).",
        ItemCategory.AP_MINE, 2, status=ReportStatus.REJECTED,
        note="Duplicate of the report from 5 October.",
    )  # fmt: skip


def seed(db: Session) -> None:
    rng = random.Random(42)
    retry_rng = random.Random(7)  # only used to relocate a blob that would collide
    qa_rng = random.Random(43)  # separate stream so QA data never shifts the hazards
    _wipe(db)
    statuses = [s for s, w in STATUS_WEIGHTS for _ in range(w)]
    placed: list[Polygon] = []

    for _ in range(HAZARD_COUNT):
        region = rng.choice(list(REGIONS))
        c_lon, c_lat = REGIONS[region]
        lon = c_lon + rng.uniform(-0.12, 0.12)
        lat = c_lat + rng.uniform(-0.12, 0.12)
        shape = _blob(rng, lon, lat, rng.uniform(80, 700))
        for _attempt in range(50):  # keep random hazards clear of each other (about 40 m)
            if not any(shape.buffer(0.0004).intersects(p) for p in placed):
                break
            lon = c_lon + retry_rng.uniform(-0.12, 0.12)
            lat = c_lat + retry_rng.uniform(-0.12, 0.12)
            shape = _blob(retry_rng, lon, lat, retry_rng.uniform(80, 700))
        placed.append(shape)

        status = rng.choice(statuses)
        hazard = _create_hazard(
            db,
            name=f"{rng.choice(NAME_PREFIX)} {rng.choice(NAME_SUFFIX)}",
            hazard_class=rng.choice(list(HazardClass)),
            status=status,
            region=region,
            geom=shape,
        )
        _add_lifecycle(db, hazard, status, rng, qa_rng)

    _topology_scenarios(db, rng, qa_rng)
    _field_reports(db)
    db.commit()
    bootstrap.ensure_demo_users(db)


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session)
        print(f"Seeded {HAZARD_COUNT} synthetic hazards plus topology test cases and demo users.")
