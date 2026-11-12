"""GeoJSON <-> shapely <-> PostGIS helpers. All geometry input goes through here."""

from typing import Any

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.validation import explain_validity
from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

SRID = 4326


class GeometryError(ValueError):
    """Raised when client-supplied geometry is unacceptable.

    `code` is a stable machine-readable reason (used in import rejection reports).
    """

    def __init__(self, message: str, code: str = "invalid_geometry") -> None:
        super().__init__(message)
        self.code = code


def parse_polygonal_geojson(geometry: dict[str, Any]) -> MultiPolygon:
    """Validate a GeoJSON Polygon/MultiPolygon and return it as a MultiPolygon."""
    try:
        geom = shape(geometry)
    except Exception as exc:  # shapely raises various types for malformed input
        raise GeometryError(f"Malformed GeoJSON geometry: {exc}") from exc

    if not isinstance(geom, Polygon | MultiPolygon):
        raise GeometryError(f"Geometry must be Polygon or MultiPolygon, got {geom.geom_type}")
    if geom.is_empty:
        raise GeometryError("Geometry is empty")

    min_x, min_y, max_x, max_y = geom.bounds
    if not (-180 <= min_x and max_x <= 180 and -90 <= min_y and max_y <= 90):
        raise GeometryError(
            "Coordinates out of range for EPSG:4326 (expected [lon, lat] with lon in "
            "[-180, 180] and lat in [-90, 90])",
            code="coordinates_out_of_range",
        )
    if not geom.is_valid:
        raise GeometryError(f"Invalid geometry: {explain_validity(geom)}")

    return MultiPolygon([geom]) if isinstance(geom, Polygon) else geom


def to_db_geometry(geom: MultiPolygon) -> Any:
    return from_shape(geom, srid=SRID)


def area_m2(db: Session, geom: MultiPolygon) -> float:
    """Geodesic area in square metres, computed by PostGIS on the spheroid."""
    stmt = select(
        cast(func.ST_Area(func.Geography(func.ST_GeomFromText(geom.wkt, SRID))), Float)
    )
    return float(db.execute(stmt).scalar_one())


def to_geojson(db_geom: Any) -> dict[str, Any]:
    return dict(mapping(to_shape(db_geom)))


def measures(db: Session, geom: MultiPolygon) -> tuple[float, float]:
    """Geodesic (area in m2, perimeter in m) of a geometry, computed by PostGIS."""
    g = func.Geography(func.ST_GeomFromText(geom.wkt, SRID))
    row = db.execute(select(cast(func.ST_Area(g), Float), cast(func.ST_Perimeter(g), Float))).one()
    return float(row[0]), float(row[1])
