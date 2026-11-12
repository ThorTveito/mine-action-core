"""Deterministic synthetic data for the fictional country of Karvonia.

Run with: python -m app.seed   (destructive: wipes hazards, tasks, records)

Nothing here is real. Coordinates are an arbitrary patch of land chosen only so
the map has something to show; region and organisation names are invented.
"""

import math
import random
from datetime import date, timedelta

from shapely.geometry import Polygon
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import audit, geo
from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    ClearanceRecord,
    Hazard,
    HazardClass,
    HazardStatus,
    HazardType,
    Task,
    TaskStatus,
    TaskType,
)

REGIONS = {  # name -> (lon, lat) centre
    "Northern Marches": (18.20, 15.55),
    "Eastern Uplands": (18.75, 15.10),
    "Central Basin": (18.15, 15.05),
    "Southern Plains": (18.10, 14.55),
    "River Delta": (17.60, 14.95),
    "Western Ridge": (17.50, 15.45),
}
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
    db.execute(text("TRUNCATE audit_log, clearance_records, tasks, hazards RESTART IDENTITY CASCADE"))


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
) -> None:
    """Split `fraction` of `total_area` into dated clearance records."""
    remaining = total_area * fraction
    day = task.planned_start or date(2025, 1, 1)
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
        day += timedelta(days=rng.randint(1, 4))


def seed(db: Session) -> None:
    rng = random.Random(42)
    _wipe(db)
    statuses = [s for s, w in STATUS_WEIGHTS for _ in range(w)]

    for _ in range(HAZARD_COUNT):
        region = rng.choice(list(REGIONS))
        c_lon, c_lat = REGIONS[region]
        lon = c_lon + rng.uniform(-0.12, 0.12)
        lat = c_lat + rng.uniform(-0.12, 0.12)
        geom = geo.parse_polygonal_geojson(
            _blob(rng, lon, lat, rng.uniform(80, 700)).__geo_interface__
        )
        status = rng.choice(statuses)
        hazard = Hazard(
            name=f"{rng.choice(NAME_PREFIX)} {rng.choice(NAME_SUFFIX)}",
            hazard_type=HazardType.SHA if status == HazardStatus.SUSPECTED else HazardType.CHA,
            hazard_class=rng.choice(list(HazardClass)),
            status=status,
            region=region,
            description="Synthetic hazard record for demonstration.",
            geom=geo.to_db_geometry(geom),
            area_m2=geo.area_m2(db, geom),
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

        match status:
            case HazardStatus.SUSPECTED:
                if rng.random() < 0.5:
                    _add_task(db, hazard, TaskType.SURVEY, TaskStatus.PLANNED, rng)
            case HazardStatus.CONFIRMED:
                _add_task(db, hazard, TaskType.CLEARANCE, TaskStatus.PLANNED, rng)
            case HazardStatus.IN_CLEARANCE:
                task = _add_task(db, hazard, TaskType.CLEARANCE, TaskStatus.ACTIVE, rng)
                _add_records(db, task, hazard.area_m2, rng.uniform(0.15, 0.8), rng)
            case HazardStatus.RELEASED:
                task = _add_task(db, hazard, TaskType.CLEARANCE, TaskStatus.COMPLETED, rng)
                _add_records(db, task, hazard.area_m2, 1.0, rng)
                _add_task(db, hazard, TaskType.VERIFICATION, TaskStatus.COMPLETED, rng)
            case HazardStatus.CANCELLED:
                _add_task(db, hazard, TaskType.SURVEY, TaskStatus.COMPLETED, rng)

    db.commit()


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session)
        print(f"Seeded {HAZARD_COUNT} synthetic hazards.")
