"""Admin areas: hazards get their region from the polygon they lie in."""

from fastapi.testclient import TestClient
from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon, box

from app.db import SessionLocal
from app.models import AdminArea
from tests.helpers import box_geojson, make_hazard


def add_areas() -> None:
    with SessionLocal() as db:
        db.add(
            AdminArea(
                name="West",
                code="W",
                geom=from_shape(MultiPolygon([box(17.9, 14.9, 18.05, 15.1)]), srid=4326),
            )
        )
        db.add(
            AdminArea(
                name="East",
                code="E",
                geom=from_shape(MultiPolygon([box(18.05, 14.9, 18.2, 15.1)]), srid=4326),
            )
        )
        db.commit()


def test_region_is_assigned_from_the_containing_area(client: TestClient) -> None:
    add_areas()
    west = make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004), region=None)
    east = make_hazard(client, box_geojson(18.1, 15.0, 18.104, 15.004), region=None)
    outside = make_hazard(client, box_geojson(18.5, 15.0, 18.504, 15.004), region=None)
    assert (west["region"], east["region"], outside["region"]) == ("West", "East", "Unassigned")


def test_given_region_is_kept_but_a_mismatch_is_flagged(client: TestClient) -> None:
    add_areas()
    hazard = make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004), region="East")
    assert hazard["region"] == "East"
    issues = client.get("/api/topology/check").json()["issues"]
    assert [(i["rule"], i["message"]) for i in issues] == [
        ("region_mismatch", "KRV-HAZ-00001 is recorded in East but lies in West")
    ]


def test_admin_areas_endpoint_reports_contamination(client: TestClient, anon: TestClient) -> None:
    add_areas()
    make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004), region=None)
    body = anon.get("/api/admin-areas").json()
    by_name = {f["properties"]["name"]: f["properties"] for f in body["features"]}
    assert by_name["West"]["open_hazards"] == 1 and by_name["West"]["contaminated_m2"] > 0
    assert by_name["East"]["open_hazards"] == 0
    assert body["features"][0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}


def test_import_derives_region(client: TestClient) -> None:
    add_areas()
    csv = 'name,hazard_type,hazard_class,wkt\nA,SHA,uxo,"POLYGON((18.1 15, 18.104 15, 18.104 15.004, 18.1 15.004, 18.1 15))"\n'
    report = client.post(
        "/api/imports/hazards",
        files={"file": ("a.csv", csv, "text/csv")},
        data={"dry_run": "false"},
    ).json()
    assert report["created"] == 1
    assert client.get("/api/hazards").json()[0]["region"] == "East"
