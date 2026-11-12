"""Field reports: findings registered by surveyors, triaged by IM staff.

Flow: a surveyor submits a report (works offline on the device; resending is idempotent via
`client_id`). Staff look at nearby hazards, then either turn the report into a new suspected
hazard area, link it to an existing hazard, or reject it. Every step is audited.
"""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from geoalchemy2.shape import from_shape, to_shape
from shapely import wkt as shapely_wkt
from shapely.geometry import Point, mapping
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import audit, geo, topology
from app.auth import CurrentUser, Permission, ensure, has_permission
from app.config import get_settings
from app.db import get_db
from app.models import (
    FieldReport,
    Hazard,
    HazardClass,
    HazardStatus,
    HazardType,
    ItemCategory,
    ReportStatus,
    User,
)
from app.schemas import (
    AcceptReport,
    FieldReportCreate,
    FieldReportRead,
    NearbyHazard,
    RejectReport,
    ReportDecision,
)

router = APIRouter(prefix="/field-reports", tags=["field reports"])
DbDep = Annotated[Session, Depends(get_db)]

_CLASS_FOR_ITEM: dict[ItemCategory | None, HazardClass] = {
    ItemCategory.AP_MINE: HazardClass.ANTI_PERSONNEL,
    ItemCategory.AV_MINE: HazardClass.ANTI_VEHICLE,
    ItemCategory.SUBMUNITION: HazardClass.CLUSTER_MUNITION,
    ItemCategory.UXO: HazardClass.UXO,
}


def to_read(r: FieldReport) -> FieldReportRead:
    point = to_shape(r.location)
    return FieldReportRead(
        id=r.id,
        code=r.code or "",
        client_id=r.client_id,
        reported_by=r.reported_by,
        observed_at=r.observed_at,
        received_at=r.received_at,
        finding_type=r.finding_type,
        item_category=r.item_category,
        quantity=r.quantity,
        source=r.source,
        description=r.description,
        lon=point.x,
        lat=point.y,
        gps_accuracy_m=r.gps_accuracy_m,
        region=r.region,
        status=r.status,
        reviewed_by=r.reviewed_by,
        reviewed_at=r.reviewed_at,
        review_note=r.review_note,
        hazard_id=r.hazard_id,
        hazard_code=r.hazard.code if r.hazard else None,
    )


def _visible(stmt: Any, user: User) -> Any:
    """Staff see every report; everyone else with REPORT sees only their own."""
    if has_permission(user, Permission.VIEW_REPORTS):
        return stmt
    if has_permission(user, Permission.REPORT):
        return stmt.where(FieldReport.reported_by == user.username)
    raise HTTPException(
        status.HTTP_403_FORBIDDEN, detail=f"Role '{user.role.value}' may not view field reports"
    )


def _get_visible(db: Session, report_id: int, user: User) -> FieldReport:
    report = db.scalar(_visible(select(FieldReport), user).where(FieldReport.id == report_id))
    if report is None:  # 404 rather than 403, so ids of other people's reports don't leak
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Field report {report_id} not found")
    return report


@router.post("", response_model=FieldReportRead, status_code=status.HTTP_201_CREATED)
def submit_report(
    payload: FieldReportCreate, db: DbDep, user: CurrentUser, response: Response
) -> FieldReportRead:
    """Register a finding. Resending the same `client_id` returns the stored report (200)."""
    ensure(user, Permission.REPORT, "field reporting")
    existing = db.scalar(select(FieldReport).where(FieldReport.client_id == payload.client_id))
    if existing is not None:
        if existing.reported_by != user.username:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="client_id already used")
        response.status_code = status.HTTP_200_OK
        return to_read(existing)

    values = payload.model_dump(exclude={"lon", "lat"})
    report = FieldReport(
        **values,
        reported_by=user.username,
        location=from_shape(Point(payload.lon, payload.lat), srid=geo.SRID),
    )
    db.add(report)
    db.flush()
    report.code = f"{get_settings().country_code}-FR-{report.id:05d}"
    audit.record(
        db,
        "field_report",
        report.id,
        "create",
        audit.created_values(
            {
                "code": report.code,
                "finding_type": payload.finding_type,
                "lon": payload.lon,
                "lat": payload.lat,
            }
        ),
        actor=user.username,
    )
    db.commit()
    db.refresh(report)
    return to_read(report)


@router.get("", response_model=list[FieldReportRead])
def list_reports(
    db: DbDep,
    user: CurrentUser,
    status_: Annotated[ReportStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FieldReportRead]:
    """Newest first. Surveyors get their own reports; staff get all of them."""
    stmt = _visible(select(FieldReport), user)
    if status_:
        stmt = stmt.where(FieldReport.status == status_)
    stmt = stmt.order_by(FieldReport.observed_at.desc(), FieldReport.id.desc())
    return [to_read(r) for r in db.scalars(stmt.limit(limit).offset(offset)).all()]


@router.get("/geojson")
def reports_geojson(db: DbDep, user: CurrentUser) -> dict[str, Any]:
    """Visible reports as GeoJSON points, for the map."""
    rows = db.scalars(_visible(select(FieldReport), user).order_by(FieldReport.id)).all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": r.id,
                "geometry": dict(mapping(to_shape(r.location))),
                "properties": {
                    "id": r.id,
                    "code": r.code,
                    "status": r.status.value,
                    "finding_type": r.finding_type.value,
                    "item_category": r.item_category.value if r.item_category else None,
                    "reported_by": r.reported_by,
                },
            }
            for r in rows
        ],
    }


@router.get("/{report_id}", response_model=FieldReportRead)
def get_report(report_id: int, db: DbDep, user: CurrentUser) -> FieldReportRead:
    return to_read(_get_visible(db, report_id, user))


_NEARBY_SQL = text(
    """
    WITH p AS (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS g)
    SELECT h.id, h.code, h.name, h.status, h.region,
           ST_Distance(h.geom::geography, p.g::geography) AS distance_m,
           ST_Contains(h.geom, p.g) AS contains_point
    FROM hazards h, p
    WHERE ST_DWithin(h.geom, p.g, :deg)
      AND ST_DWithin(h.geom::geography, p.g::geography, :radius)
    ORDER BY distance_m, h.id
    LIMIT 10
    """
)


def nearby_hazards(db: Session, lon: float, lat: float, radius_m: float) -> list[NearbyHazard]:
    params = {"lon": lon, "lat": lat, "radius": radius_m, "deg": radius_m / 111_000 * 3}
    return [
        NearbyHazard(
            id=r.id,
            code=r.code,
            name=r.name,
            status=HazardStatus(r.status),
            region=r.region,
            distance_m=float(r.distance_m),
            contains_point=bool(r.contains_point),
        )
        for r in db.execute(_NEARBY_SQL, params)
    ]


@router.get("/{report_id}/nearby", response_model=list[NearbyHazard])
def report_nearby(
    report_id: int,
    db: DbDep,
    user: CurrentUser,
    radius_m: Annotated[float, Query(ge=10, le=10_000)] = 500,
) -> list[NearbyHazard]:
    """Hazards within `radius_m` of the report, nearest first (helps decide link vs new)."""
    ensure(user, Permission.VIEW_REPORTS, "reviewing field reports")
    point = to_shape(_get_visible(db, report_id, user).location)
    return nearby_hazards(db, point.x, point.y, radius_m)


def _released_warnings(db: Session, lon: float, lat: float) -> list[str]:
    return [
        f"The point lies inside RELEASED hazard {h.code}: residual contamination in released "
        "land must be investigated (QA failure?)"
        for h in nearby_hazards(db, lon, lat, 10)
        if h.contains_point and h.status == HazardStatus.RELEASED
    ]


def _require_submitted(report: FieldReport) -> None:
    if report.status != ReportStatus.SUBMITTED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Report {report.code} was already {report.status.value}",
        )


@router.post("/{report_id}/accept", response_model=ReportDecision)
def accept_report(
    report_id: int, payload: AcceptReport, db: DbDep, user: CurrentUser
) -> ReportDecision:
    """Turn the report into a new suspected hazard, or link it to an existing hazard."""
    ensure(user, Permission.WRITE, "reviewing field reports")
    report = _get_visible(db, report_id, user)
    _require_submitted(report)
    point = to_shape(report.location)
    warnings = _released_warnings(db, point.x, point.y)
    source = f"field_report:{report.code}"

    if payload.mode == "link":
        hazard = db.get(Hazard, payload.hazard_id)
        if hazard is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"Hazard {payload.hazard_id} not found"
            )
        if hazard.status == HazardStatus.CANCELLED:
            warnings.append(f"{hazard.code} is cancelled; consider a new hazard instead")
    else:
        hazard = _new_hazard_from_report(db, report, payload, user, source)
        _, issues = topology.check(db, hazard.id)
        warnings += [i.message for i in issues if i.severity == "error"]

    trail = audit.diff(
        report,
        {"status": ReportStatus.ACCEPTED, "hazard_id": hazard.id, "reviewed_by": user.username},
    )
    report.status = ReportStatus.ACCEPTED
    report.hazard_id = hazard.id
    report.reviewed_by = user.username
    report.reviewed_at = datetime.now(UTC)
    report.review_note = payload.note
    audit.record(db, "field_report", report.id, "update", trail, source="api", actor=user.username)
    db.commit()
    db.refresh(report)
    return ReportDecision(report=to_read(report), hazard_id=hazard.id, warnings=warnings)


def _new_hazard_from_report(
    db: Session, report: FieldReport, payload: AcceptReport, user: User, source: str
) -> Hazard:
    point = to_shape(report.location)
    wkt = db.execute(
        text(
            "SELECT ST_AsText(ST_Multi(ST_Buffer("
            "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :r, 'quad_segs=8')::geometry))"
        ),
        {"lon": point.x, "lat": point.y, "r": payload.radius_m},
    ).scalar_one()
    geom = geo.parse_polygonal_geojson(dict(mapping(shapely_wkt.loads(wkt))))
    region = payload.region or report.region or _nearest_region(db, point.x, point.y)
    hazard = Hazard(
        name=payload.name or f"Field report {report.code}",  # no names on public data
        hazard_type=HazardType.SHA,
        hazard_class=_CLASS_FOR_ITEM.get(report.item_category, HazardClass.MIXED),
        status=HazardStatus.SUSPECTED,
        region=region,
        # Only a reference: the report's own text can name informants and stays private.
        description=f"Created from field report {report.code} ({report.finding_type.value}).",
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
        audit.created_values(
            {"code": hazard.code, "status": hazard.status, "area_m2": hazard.area_m2}
        ),
        source=source,
        actor=user.username,
    )
    return hazard


def _nearest_region(db: Session, lon: float, lat: float) -> str:
    """Region of the nearest existing hazard (KNN on the spatial index), else 'Unassigned'."""
    region = db.execute(
        text(
            "SELECT region FROM hazards "
            "ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) LIMIT 1"
        ),
        {"lon": lon, "lat": lat},
    ).scalar()
    return region or "Unassigned"


@router.post("/{report_id}/reject", response_model=ReportDecision)
def reject_report(
    report_id: int, payload: RejectReport, db: DbDep, user: CurrentUser
) -> ReportDecision:
    """Close a report without creating data (duplicate, not credible, outside the area...)."""
    ensure(user, Permission.WRITE, "reviewing field reports")
    report = _get_visible(db, report_id, user)
    _require_submitted(report)
    trail = audit.diff(report, {"status": ReportStatus.REJECTED, "reviewed_by": user.username})
    report.status = ReportStatus.REJECTED
    report.reviewed_by = user.username
    report.reviewed_at = datetime.now(UTC)
    report.review_note = payload.reason
    trail["review_note"] = [None, payload.reason]
    audit.record(db, "field_report", report.id, "update", trail, actor=user.username)
    db.commit()
    db.refresh(report)
    return ReportDecision(report=to_read(report), hazard_id=None, warnings=[])
