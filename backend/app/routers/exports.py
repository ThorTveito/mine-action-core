"""Downloadable data and donor-style reports. Public, like the other read endpoints."""

import csv
import io
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import analytics, geo
from app.db import get_db
from app.models import ClearanceRecord, Hazard, Task
from app.routers.stats import get_dashboard
from app.schemas import (
    AnnualReport,
    Casualties,
    LandRelease,
    QaSummary,
    RegionSnapshot,
    RiskEducationSummary,
)

router = APIRouter(tags=["exports"])
DbDep = Annotated[Session, Depends(get_db)]

HAZARD_COLUMNS = [
    "code",
    "name",
    "hazard_type",
    "hazard_class",
    "status",
    "region",
    "description",
    "wkt",
]  # fmt: skip: same columns the importer reads, so an export can be re-imported


def safe_cell(value: Any) -> Any:
    """Neutralise spreadsheet formula injection: text starting with = + - @ is prefixed."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _csv_response(filename: str, header: list[str], rows: list[list[Any]]) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(v) for v in row])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/exports/hazards.csv")
def export_hazards_csv(db: DbDep) -> Response:
    """Every hazard with its geometry as WKT. Re-importable via the import endpoint."""
    hazards = db.scalars(select(Hazard).order_by(Hazard.id)).all()
    rows = [
        [
            h.code, h.name, h.hazard_type.value, h.hazard_class.value, h.status.value,
            h.region, h.description or "", to_shape(h.geom).wkt,
        ]
        for h in hazards
    ]  # fmt: skip
    return _csv_response(f"hazards-{date.today().isoformat()}.csv", HAZARD_COLUMNS, rows)


@router.get("/exports/hazards.geojson")
def export_hazards_geojson(db: DbDep) -> Response:
    import json

    hazards = db.scalars(select(Hazard).order_by(Hazard.id)).all()
    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": h.id,
                "geometry": geo.to_geojson(h.geom),
                "properties": {
                    "code": h.code,
                    "name": h.name,
                    "hazard_type": h.hazard_type.value,
                    "hazard_class": h.hazard_class.value,
                    "status": h.status.value,
                    "region": h.region,
                    "description": h.description,
                    "area_m2": round(h.area_m2, 1),
                },
            }
            for h in hazards
        ],
    }
    return Response(
        content=json.dumps(collection),
        media_type="application/geo+json",
        headers={
            "Content-Disposition": f'attachment; filename="hazards-{date.today().isoformat()}.geojson"'
        },
    )


@router.get("/reports/progress.csv")
def progress_report(db: DbDep) -> Response:
    """Release progress per region (areas in square metres), with a total row."""
    dash = get_dashboard(db)
    header = [
        "region", "hazards", "contaminated_area_m2", "released_area_m2",
        "remaining_area_m2", "cleared_area_m2", "release_percent",
    ]  # fmt: skip

    def pct(released: float, total: float) -> float:
        return round(100 * released / total, 1) if total else 0.0

    rows: list[list[Any]] = [
        [
            r.region, r.hazard_count, round(r.total_area_m2), round(r.released_area_m2),
            round(r.remaining_area_m2), round(r.cleared_area_m2),
            pct(r.released_area_m2, r.total_area_m2),
        ]
        for r in dash.by_region
    ]  # fmt: skip
    rows.append(
        [
            "TOTAL", sum(r.hazard_count for r in dash.by_region), round(dash.contaminated_area_m2),
            round(dash.released_area_m2), round(dash.remaining_area_m2),
            round(sum(r.cleared_area_m2 for r in dash.by_region)), dash.release_percent,
        ]
    )  # fmt: skip
    return _csv_response(f"progress-report-{date.today().isoformat()}.csv", header, rows)


@router.get("/reports/annual", response_model=AnnualReport)
def annual_report(
    db: DbDep, year: Annotated[int, Query(ge=1990, le=2100)] = date.today().year
) -> AnnualReport:
    """An annual summary in the spirit of treaty transparency reporting (e.g. APMBC Article 7).

    Land release, casualties, risk education and QA are for `year`; contamination figures
    are the current state.
    """
    regions = list(db.scalars(select(Hazard.region).distinct().order_by(Hazard.region)))
    snapshots = []
    for region in regions:
        release = analytics.land_release(db, region, year)
        open_count = db.scalar(
            select(func.count())
            .select_from(Hazard)
            .where(Hazard.region == region, Hazard.status.in_(analytics.OPEN))
        )
        snapshots.append(
            RegionSnapshot(
                region=region,
                open_hazards=int(open_count or 0),
                outstanding_m2=analytics.outstanding_area(db, region),
                cancelled_m2=release["cancelled_m2"],
                reduced_m2=release["reduced_m2"],
                cleared_m2=release["cleared_m2"],
            )
        )
    return AnnualReport(
        year=year,
        country="Karvonia (fictional; synthetic data)",
        generated_at=datetime.now(UTC),
        open_hazards=sum(s.open_hazards for s in snapshots),
        outstanding_m2=analytics.outstanding_area(db),
        regions=snapshots,
        land_release=LandRelease(**analytics.land_release(db, None, year)),
        casualties=Casualties(**analytics.casualties(db, None, year)),
        risk_education=RiskEducationSummary(**analytics.risk_education(db, None, year)),
        qa=QaSummary(**analytics.qa_summary(db, None, year)),
    )


@router.get("/reports/clearance.csv")
def clearance_report(db: DbDep) -> Response:
    """One line per clearance record: who cleared how much, where, and what they found."""
    stmt = (
        select(Hazard, Task, ClearanceRecord)
        .join(Task, Task.hazard_id == Hazard.id)
        .join(ClearanceRecord, ClearanceRecord.task_id == Task.id)
        .order_by(ClearanceRecord.record_date, ClearanceRecord.id)
    )
    header = [
        "hazard_code", "hazard_name", "region", "task_code", "organisation", "record_date",
        "team", "release_method", "area_released_m2", "items_found", "items_destroyed",
    ]  # fmt: skip
    rows = [
        [
            h.code, h.name, h.region, t.code, t.organisation, r.record_date.isoformat(),
            r.team, r.release_method.value, round(r.area_cleared_m2, 1), r.items_found,
            r.items_destroyed,
        ]
        for h, t, r in db.execute(stmt)
    ]  # fmt: skip
    return _csv_response(f"clearance-report-{date.today().isoformat()}.csv", header, rows)
