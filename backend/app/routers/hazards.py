from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, geo, rules
from app.config import get_settings
from app.db import get_db
from app.models import Hazard, HazardClass, HazardStatus, HazardType
from app.schemas import HazardCreate, HazardRead, HazardUpdate

router = APIRouter(prefix="/hazards", tags=["hazards"])
DbDep = Annotated[Session, Depends(get_db)]


def to_read(h: Hazard) -> HazardRead:
    return HazardRead(
        id=h.id,
        code=h.code or "",
        name=h.name,
        hazard_type=h.hazard_type,
        hazard_class=h.hazard_class,
        status=h.status,
        region=h.region,
        description=h.description,
        area_m2=h.area_m2,
        geometry=geo.to_geojson(h.geom),
        created_at=h.created_at,
        updated_at=h.updated_at,
    )


def _parse_geometry(geometry: dict[str, Any]) -> Any:
    try:
        return geo.parse_polygonal_geojson(geometry)
    except geo.GeometryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


def _get_or_404(db: Session, hazard_id: int) -> Hazard:
    hazard = db.get(Hazard, hazard_id)
    if hazard is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Hazard {hazard_id} not found")
    return hazard


def _filtered(
    stmt: Any,
    status_: HazardStatus | None,
    region: str | None,
    hazard_type: HazardType | None,
    hazard_class: HazardClass | None,
) -> Any:
    if status_:
        stmt = stmt.where(Hazard.status == status_)
    if region:
        stmt = stmt.where(Hazard.region == region)
    if hazard_type:
        stmt = stmt.where(Hazard.hazard_type == hazard_type)
    if hazard_class:
        stmt = stmt.where(Hazard.hazard_class == hazard_class)
    return stmt


@router.get("", response_model=list[HazardRead])
def list_hazards(
    db: DbDep,
    status_: Annotated[HazardStatus | None, Query(alias="status")] = None,
    region: str | None = None,
    hazard_type: HazardType | None = None,
    hazard_class: HazardClass | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[HazardRead]:
    stmt = _filtered(select(Hazard), status_, region, hazard_type, hazard_class)
    rows = db.scalars(stmt.order_by(Hazard.id).limit(limit).offset(offset)).all()
    return [to_read(h) for h in rows]


@router.get("/geojson")
def hazards_geojson(
    db: DbDep,
    status_: Annotated[HazardStatus | None, Query(alias="status")] = None,
    region: str | None = None,
    hazard_type: HazardType | None = None,
    hazard_class: HazardClass | None = None,
) -> dict[str, Any]:
    """All matching hazards as a GeoJSON FeatureCollection (for the map)."""
    stmt = _filtered(select(Hazard), status_, region, hazard_type, hazard_class)
    features = [
        {
            "type": "Feature",
            "id": h.id,
            "geometry": geo.to_geojson(h.geom),
            "properties": {
                "id": h.id,
                "code": h.code,
                "name": h.name,
                "hazard_type": h.hazard_type.value,
                "hazard_class": h.hazard_class.value,
                "status": h.status.value,
                "region": h.region,
                "area_m2": h.area_m2,
            },
        }
        for h in db.scalars(stmt.order_by(Hazard.id)).all()
    ]
    return {"type": "FeatureCollection", "features": features}


@router.get("/{hazard_id}", response_model=HazardRead)
def get_hazard(hazard_id: int, db: DbDep) -> HazardRead:
    return to_read(_get_or_404(db, hazard_id))


@router.post("", response_model=HazardRead, status_code=status.HTTP_201_CREATED)
def create_hazard(payload: HazardCreate, db: DbDep) -> HazardRead:
    if (msg := rules.check_initial_status(payload.status)) is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=msg)
    geom = _parse_geometry(payload.geometry)
    values = payload.model_dump(exclude={"geometry"})
    hazard = Hazard(**values, geom=geo.to_db_geometry(geom), area_m2=geo.area_m2(db, geom))
    db.add(hazard)
    db.flush()
    hazard.code = f"{get_settings().country_code}-HAZ-{hazard.id:05d}"
    audit.record(
        db,
        "hazard",
        hazard.id,
        "create",
        audit.created_values({**values, "code": hazard.code, "area_m2": hazard.area_m2}),
    )
    db.commit()
    db.refresh(hazard)
    return to_read(hazard)


@router.patch("/{hazard_id}", response_model=HazardRead)
def update_hazard(hazard_id: int, payload: HazardUpdate, db: DbDep) -> HazardRead:
    hazard = _get_or_404(db, hazard_id)
    changes = payload.model_dump(exclude_unset=True, exclude={"geometry"})
    for field, value in changes.items():
        if value is None and field in {"name", "hazard_type", "hazard_class", "status", "region"}:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{field} cannot be null"
            )
    if "status" in changes and changes["status"] != hazard.status:
        if (msg := rules.check_status_change(db, hazard, changes["status"])) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=msg)

    if payload.geometry is not None:
        geom = _parse_geometry(payload.geometry)
        new_area = geo.area_m2(db, geom)
        trail = audit.diff(hazard, {**changes, "area_m2": new_area})
        trail["geometry"] = ["(previous)", "(updated)"]
        hazard.geom = geo.to_db_geometry(geom)
        hazard.area_m2 = new_area
    else:
        trail = audit.diff(hazard, changes)
    for field, value in changes.items():
        setattr(hazard, field, value)
    if trail:
        audit.record(db, "hazard", hazard.id, "update", trail)
    db.commit()
    db.refresh(hazard)
    return to_read(hazard)


@router.delete("/{hazard_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hazard(hazard_id: int, db: DbDep) -> Response:
    hazard = _get_or_404(db, hazard_id)
    audit.record(db, "hazard", hazard.id, "delete", {"code": [hazard.code, None]})
    db.delete(hazard)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
