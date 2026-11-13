"""Accidents (with victims) and explosive ordnance risk education (EORE) sessions.

Victims are recorded without names or other identifiers: sex, age and outcome are what
sex- and age-disaggregated reporting needs, and nothing more is collected. Individual
accident records are visible to staff only; the public sees aggregates on the dashboard.
EORE sessions hold no personal data and are public.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, mapping
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app import audit, gazetteer, geo
from app.auth import CurrentUser, Permission, ensure, require
from app.config import get_settings
from app.db import get_db
from app.models import Accident, RiskEducationSession, User, Victim, VictimOutcome
from app.schemas import (
    AccidentCreate,
    AccidentRead,
    RiskEducationCreate,
    RiskEducationRead,
    VictimIn,
    VictimOut,
)

router = APIRouter(tags=["accidents & risk education"])
DbDep = Annotated[Session, Depends(get_db)]

# A hazard within this distance of an accident is linked to it automatically.
LINK_DISTANCE_M = 500

_NEAREST_HAZARD = text(
    """
    WITH p AS (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS g)
    SELECT h.id FROM hazards h, p
    WHERE ST_DWithin(h.geom, p.g, :deg)
      AND ST_DWithin(h.geom::geography, p.g::geography, :m)
    ORDER BY ST_Contains(h.geom, p.g) DESC, ST_Distance(h.geom::geography, p.g::geography)
    LIMIT 1
    """
)


def nearest_hazard_id(db: Session, lon: float, lat: float) -> int | None:
    """The hazard containing the point, else the nearest within LINK_DISTANCE_M."""
    params = {"lon": lon, "lat": lat, "m": LINK_DISTANCE_M, "deg": LINK_DISTANCE_M / 111_000 * 3}
    return db.execute(_NEAREST_HAZARD, params).scalar()


def accident_to_read(a: Accident) -> AccidentRead:
    p = to_shape(a.location)
    return AccidentRead(
        id=a.id,
        code=a.code or "",
        occurred_on=a.occurred_on,
        lon=p.x,
        lat=p.y,
        region=a.region,
        item_category=a.item_category,
        activity=a.activity,
        description=a.description,
        hazard_id=a.hazard_id,
        hazard_code=a.hazard.code if a.hazard else None,
        field_report_id=a.field_report_id,
        recorded_by=a.recorded_by,
        killed=sum(1 for v in a.victims if v.outcome == VictimOutcome.KILLED),
        injured=sum(1 for v in a.victims if v.outcome == VictimOutcome.INJURED),
        victims=[VictimOut.model_validate(v) for v in a.victims],
    )


def create_accident(
    db: Session,
    *,
    occurred_on: Any,
    lon: float,
    lat: float,
    item_category: Any,
    activity: Any,
    description: str,
    victims: list[VictimIn],
    actor: str,
    source: str = "api",
    field_report_id: int | None = None,
) -> Accident:
    """Shared by the accident endpoint and field-report triage."""
    point = Point(lon, lat)
    accident = Accident(
        occurred_on=occurred_on,
        location=from_shape(point, srid=geo.SRID),
        region=gazetteer.area_for(db, point),
        item_category=item_category,
        activity=activity,
        description=description,
        hazard_id=nearest_hazard_id(db, lon, lat),
        field_report_id=field_report_id,
        recorded_by=actor,
        victims=[Victim(**v.model_dump()) for v in victims],
    )
    db.add(accident)
    db.flush()
    accident.code = f"{get_settings().country_code}-ACC-{accident.id:05d}"
    audit.record(
        db,
        "accident",
        accident.id,
        "create",
        audit.created_values(
            {
                "code": accident.code,
                "occurred_on": occurred_on,
                "victims": len(victims),
                "hazard_id": accident.hazard_id,
            }
        ),
        source=source,
        actor=actor,
    )
    return accident


# ------------------------------------------------------------------------------ accidents


@router.get("/accidents", response_model=list[AccidentRead])
def list_accidents(
    db: DbDep,
    user: CurrentUser,
    year: Annotated[int | None, Query(ge=1900, le=2100)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[AccidentRead]:
    """Staff only. Newest first."""
    ensure(user, Permission.VIEW_REPORTS, "viewing accident records")
    stmt = select(Accident).options(selectinload(Accident.victims), selectinload(Accident.hazard))
    if year is not None:
        stmt = stmt.where(text("EXTRACT(YEAR FROM occurred_on) = :y").bindparams(y=year))
    stmt = stmt.order_by(Accident.occurred_on.desc(), Accident.id.desc()).limit(limit)
    return [accident_to_read(a) for a in db.scalars(stmt).all()]


@router.get("/accidents/geojson")
def accidents_geojson(db: DbDep, user: CurrentUser) -> dict[str, Any]:
    ensure(user, Permission.VIEW_REPORTS, "viewing accident records")
    rows = db.scalars(select(Accident).options(selectinload(Accident.victims))).all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": a.id,
                "geometry": dict(mapping(to_shape(a.location))),
                "properties": {
                    "id": a.id,
                    "code": a.code,
                    "occurred_on": a.occurred_on.isoformat(),
                    "killed": sum(1 for v in a.victims if v.outcome == VictimOutcome.KILLED),
                    "injured": sum(1 for v in a.victims if v.outcome == VictimOutcome.INJURED),
                },
            }
            for a in rows
        ],
    }


@router.get("/accidents/{accident_id}", response_model=AccidentRead)
def get_accident(accident_id: int, db: DbDep, user: CurrentUser) -> AccidentRead:
    ensure(user, Permission.VIEW_REPORTS, "viewing accident records")
    accident = db.get(Accident, accident_id)
    if accident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Accident {accident_id} not found")
    return accident_to_read(accident)


@router.post("/accidents", response_model=AccidentRead, status_code=status.HTTP_201_CREATED)
def post_accident(
    payload: AccidentCreate,
    db: DbDep,
    user: Annotated[User, Depends(require(Permission.WRITE))],
) -> AccidentRead:
    """Record an accident and its victims. The nearest hazard (within 500 m) is linked."""
    accident = create_accident(
        db,
        occurred_on=payload.occurred_on,
        lon=payload.lon,
        lat=payload.lat,
        item_category=payload.item_category,
        activity=payload.activity,
        description=payload.description,
        victims=payload.victims,
        actor=user.username,
    )
    db.commit()
    db.refresh(accident)
    return accident_to_read(accident)


@router.delete("/accidents/{accident_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_accident(
    accident_id: int, db: DbDep, user: Annotated[User, Depends(require(Permission.DELETE))]
) -> Response:
    accident = db.get(Accident, accident_id)
    if accident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Accident {accident_id} not found")
    audit.record(
        db, "accident", accident.id, "delete", {"code": [accident.code, None]}, actor=user.username
    )
    db.delete(accident)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------------- risk education


def eore_to_read(s: RiskEducationSession) -> RiskEducationRead:
    p = to_shape(s.location)
    return RiskEducationRead(
        id=s.id,
        code=s.code or "",
        held_on=s.held_on,
        lon=p.x,
        lat=p.y,
        region=s.region,
        organisation=s.organisation,
        girls=s.girls,
        boys=s.boys,
        women=s.women,
        men=s.men,
        total=s.girls + s.boys + s.women + s.men,
        notes=s.notes,
    )


@router.get("/risk-education", response_model=list[RiskEducationRead])
def list_sessions(
    db: DbDep,
    region: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[RiskEducationRead]:
    """Public: sessions hold counts only, no personal data. Newest first."""
    stmt = select(RiskEducationSession)
    if region:
        stmt = stmt.where(RiskEducationSession.region == region)
    stmt = stmt.order_by(RiskEducationSession.held_on.desc(), RiskEducationSession.id.desc())
    return [eore_to_read(s) for s in db.scalars(stmt.limit(limit)).all()]


@router.post(
    "/risk-education", response_model=RiskEducationRead, status_code=status.HTTP_201_CREATED
)
def post_session(
    payload: RiskEducationCreate,
    db: DbDep,
    user: Annotated[User, Depends(require(Permission.WRITE))],
) -> RiskEducationRead:
    point = Point(payload.lon, payload.lat)
    values = payload.model_dump(exclude={"lon", "lat"})
    session = RiskEducationSession(
        **values,
        location=from_shape(point, srid=geo.SRID),
        region=gazetteer.area_for(db, point),
        recorded_by=user.username,
    )
    db.add(session)
    db.flush()
    session.code = f"{get_settings().country_code}-EORE-{session.id:05d}"
    audit.record(
        db,
        "risk_education",
        session.id,
        "create",
        audit.created_values({"code": session.code, **values}),
        actor=user.username,
    )
    db.commit()
    db.refresh(session)
    return eore_to_read(session)


@router.delete("/risk-education/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int, db: DbDep, user: Annotated[User, Depends(require(Permission.DELETE))]
) -> Response:
    session = db.get(RiskEducationSession, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found")
    audit.record(
        db,
        "risk_education",
        session.id,
        "delete",
        {"code": [session.code, None]},
        actor=user.username,
    )
    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------- admin areas


@router.get("/admin-areas")
def admin_areas(db: DbDep) -> dict[str, Any]:
    """Public. Simplified boundaries with each area's hazard figures, for maps and choropleths."""
    rows = db.execute(
        text(
            """
            SELECT a.id, a.name, a.code,
                   ST_AsGeoJSON(ST_SimplifyPreserveTopology(a.geom, 0.0005), 6)::json AS geometry,
                   ST_Area(a.geom::geography) AS area_m2,
                   COUNT(h.id) FILTER (WHERE h.status IN ('suspected','confirmed','in_clearance'))
                       AS open_hazards,
                   COALESCE(SUM(h.area_m2) FILTER (
                       WHERE h.status IN ('suspected','confirmed','in_clearance')), 0)
                       AS contaminated_m2
            FROM admin_areas a
            LEFT JOIN hazards h ON h.region = a.name
            GROUP BY a.id
            ORDER BY a.name
            """
        )
    ).all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": r.id,
                "geometry": r.geometry,
                "properties": {
                    "id": r.id,
                    "name": r.name,
                    "code": r.code,
                    "area_m2": float(r.area_m2),
                    "open_hazards": int(r.open_hazards),
                    "contaminated_m2": float(r.contaminated_m2),
                },
            }
            for r in rows
        ],
    }
