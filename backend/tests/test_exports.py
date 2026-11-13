import csv
import io
import json

from fastapi.testclient import TestClient

from app.routers.exports import safe_cell
from tests.helpers import box_geojson, make_hazard, release_hazard


def rows(res) -> list[list[str]]:
    return list(csv.reader(io.StringIO(res.text)))


def test_exports_are_public_downloads(anon: TestClient, client: TestClient) -> None:
    make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004))
    for path, kind in [
        ("/api/exports/hazards.csv", "text/csv"),
        ("/api/exports/hazards.geojson", "application/geo+json"),
        ("/api/reports/progress.csv", "text/csv"),
        ("/api/reports/clearance.csv", "text/csv"),
    ]:
        res = anon.get(path)
        assert res.status_code == 200, path
        assert res.headers["content-type"].startswith(kind)
        assert "attachment" in res.headers["content-disposition"]


def test_hazards_csv_has_import_columns_and_wkt(client: TestClient) -> None:
    make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004), name="Mill Road")
    table = rows(client.get("/api/exports/hazards.csv"))
    assert table[0] == [
        "code",
        "name",
        "hazard_type",
        "hazard_class",
        "status",
        "region",
        "description",
        "wkt",
    ]
    assert table[1][:2] == ["KRV-HAZ-00001", "Mill Road"]
    assert table[1][7].startswith("MULTIPOLYGON")


def test_export_can_be_reimported(client: TestClient) -> None:
    make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004), name="One")
    make_hazard(client, box_geojson(18.1, 15.0, 18.104, 15.004), name="Two, with comma")
    exported = client.get("/api/exports/hazards.csv").text
    report = client.post(
        "/api/imports/hazards", files={"file": ("export.csv", exported, "text/csv")}
    ).json()
    assert (report["total"], report["accepted"], report["rejected"]) == (2, 2, 0)
    assert report["updated"] == 2 and report["created"] == 0


def test_hazards_geojson_export(client: TestClient) -> None:
    make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004))
    body = json.loads(client.get("/api/exports/hazards.geojson").text)
    feature = body["features"][0]
    assert body["type"] == "FeatureCollection" and feature["properties"]["code"] == "KRV-HAZ-00001"
    assert feature["properties"]["area_m2"] > 0


def test_formula_injection_is_neutralised(client: TestClient) -> None:
    for risky in ['=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)"]:
        assert safe_cell(risky) == "'" + risky
    assert safe_cell("Normal name") == "Normal name" and safe_cell(42) == 42
    make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004), name="=cmd|' /C calc'!A0")
    assert rows(client.get("/api/exports/hazards.csv"))[1][1].startswith("'=")


def test_progress_report_has_regions_and_total(client: TestClient) -> None:
    done = make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004))
    make_hazard(client, box_geojson(18.1, 15.0, 18.104, 15.004), region="River Delta")
    release_hazard(client, done["id"], cleared=1234)
    table = rows(client.get("/api/reports/progress.csv"))
    assert table[0][0] == "region" and table[-1][0] == "TOTAL"
    by_region = {r[0]: r for r in table[1:]}
    assert by_region["Central Basin"][6] == "100.0"  # release_percent
    assert by_region["River Delta"][3] == "0"
    assert by_region["Central Basin"][5] == "1234"  # cleared_area_m2
    assert table[-1][1] == "2" and table[-1][6] == str(
        round(100 * float(table[-1][3]) / float(table[-1][2]), 1)
    )


def test_clearance_report_lists_each_record(client: TestClient) -> None:
    hazard = make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004))
    release_hazard(client, hazard["id"], cleared=500, found=2)
    table = rows(client.get("/api/reports/clearance.csv"))
    assert len(table) == 2
    record = dict(zip(table[0], table[1], strict=True))
    assert (
        record["hazard_code"] == "KRV-HAZ-00001"
        and record["area_released_m2"] == "500.0"
        and record["release_method"] == "cleared"
    )
    assert (record["items_found"], record["items_destroyed"]) == ("2", "2")
