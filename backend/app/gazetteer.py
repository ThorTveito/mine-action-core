"""Administrative areas: which region a geometry falls in (point-in-polygon on PostGIS)."""

from shapely.geometry.base import BaseGeometry
from sqlalchemy import text
from sqlalchemy.orm import Session

UNASSIGNED = "Unassigned"

_AREA_FOR_WKT = text(
    """
    SELECT a.name FROM admin_areas a
    WHERE ST_Contains(a.geom, ST_PointOnSurface(ST_GeomFromText(:wkt, 4326)))
    LIMIT 1
    """
)


def area_for(db: Session, geom: BaseGeometry) -> str | None:
    """Name of the admin area containing the geometry's representative point, if any."""
    return db.execute(_AREA_FOR_WKT, {"wkt": geom.wkt}).scalar()


def has_areas(db: Session) -> bool:
    return bool(db.execute(text("SELECT EXISTS (SELECT 1 FROM admin_areas)")).scalar())


def region_for(db: Session, geom: BaseGeometry, given: str | None = None) -> str:
    """The region to store: what the user gave, else the containing area, else Unassigned."""
    if given:
        return given
    return area_for(db, geom) or UNASSIGNED
