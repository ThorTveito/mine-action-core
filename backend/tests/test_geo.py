import pytest

from app import geo

BOWTIE = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
}


def test_polygon_is_normalised_to_multipolygon() -> None:
    result = geo.parse_polygonal_geojson(
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    )
    assert result.geom_type == "MultiPolygon"


def test_self_intersecting_ring_is_rejected() -> None:
    with pytest.raises(geo.GeometryError, match="Invalid geometry"):
        geo.parse_polygonal_geojson(BOWTIE)


def test_out_of_range_coordinates_are_rejected() -> None:
    # Looks like projected metres, a classic CRS mix-up.
    with pytest.raises(geo.GeometryError, match="out of range"):
        geo.parse_polygonal_geojson(
            {"type": "Polygon", "coordinates": [[[500000, 0], [500100, 0], [500100, 100], [500000, 0]]]}
        )


def test_non_polygon_type_is_rejected() -> None:
    with pytest.raises(geo.GeometryError, match="Polygon or MultiPolygon"):
        geo.parse_polygonal_geojson({"type": "Point", "coordinates": [18, 15]})


def test_malformed_geometry_is_rejected() -> None:
    with pytest.raises(geo.GeometryError, match="Malformed"):
        geo.parse_polygonal_geojson({"type": "Polygon"})
