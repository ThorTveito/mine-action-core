import json

from fastapi.testclient import TestClient
from pyproj import Transformer

from tests.helpers import square_wkt

HEADER = "code,name,hazard_type,hazard_class,status,region,description,wkt\n"
URL = "/api/imports/hazards"


def row(name: str, wkt: str, code: str = "", status: str = "", region: str = "Central Basin",
        htype: str = "SHA", hclass: str = "anti_personnel") -> str:
    return f'{code},{name},{htype},{hclass},{status},{region},,"{wkt}"\n'


def upload(client: TestClient, csv_text: str, **form: object):
    data = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in form.items()}
    return client.post(URL, files={"file": ("h.csv", csv_text, "text/csv")}, data=data)


def codes(report: dict, index: int, kind: str = "errors") -> list[str]:
    return [i["code"] for i in report["rows"][index - 1][kind]]


def test_dry_run_validates_but_changes_nothing(client: TestClient) -> None:
    res = upload(client, HEADER + row("A", square_wkt(18.0, 15.0)))
    report = res.json()
    assert res.status_code == 200
    assert report["dry_run"] is True and report["committed"] is False
    assert (report["total"], report["accepted"], report["created"]) == (1, 1, 1)
    assert client.get("/api/hazards").json() == []


def test_commit_creates_hazards_with_codes_and_import_audit(client: TestClient) -> None:
    csv_text = HEADER + row("A", square_wkt(18.0, 15.0)) + row("B", square_wkt(18.1, 15.1), status="confirmed")
    report = upload(client, csv_text, dry_run=False).json()
    assert report["committed"] is True and report["created"] == 2
    hazards = client.get("/api/hazards").json()
    assert [h["code"] for h in hazards] == ["KRV-HAZ-00001", "KRV-HAZ-00002"]
    assert hazards[1]["status"] == "confirmed" and hazards[0]["area_m2"] > 0
    audit = client.get("/api/audit", params={"source": f"import:{report['import_id']}"}).json()
    assert len(audit) == 2 and {a["entity_type"] for a in audit} == {"hazard"}


def test_invalid_geometry_is_rejected_with_reason(client: TestClient) -> None:
    bowtie = "POLYGON((18 15, 18.01 15.01, 18.01 15, 18 15.01, 18 15))"
    report = upload(client, HEADER + row("Bad", bowtie) + row("Good", square_wkt(18.1, 15.1))).json()
    assert (report["accepted"], report["rejected"]) == (1, 1)
    assert codes(report, 1) == ["invalid_geometry"]
    assert "Self-intersection" in report["rows"][0]["errors"][0]["message"]
    assert report["rows"][1]["outcome"] == "accepted"


def test_non_polygon_geometry_is_rejected(client: TestClient) -> None:
    report = upload(client, HEADER + row("Pt", "POINT(18 15)")).json()
    assert "Polygon or MultiPolygon" in report["rows"][0]["errors"][0]["message"]


def test_malformed_wkt_is_rejected(client: TestClient) -> None:
    report = upload(client, HEADER + row("X", "POLYGON((oops")).json()
    assert codes(report, 1) == ["invalid_geometry"]


def _utm_square() -> str:
    t = Transformer.from_crs("EPSG:4326", "EPSG:32634", always_xy=True)
    pts = [t.transform(lon, lat) for lon, lat in [(18.0, 15.0), (18.01, 15.0), (18.01, 15.01), (18.0, 15.01), (18.0, 15.0)]]
    return "POLYGON((" + ", ".join(f"{x:.2f} {y:.2f}" for x, y in pts) + "))"


def test_projected_coordinates_without_crs_are_flagged(client: TestClient) -> None:
    report = upload(client, HEADER + row("Utm", _utm_square())).json()
    assert codes(report, 1) == ["coordinates_out_of_range"]
    assert "source CRS" in report["rows"][0]["errors"][0]["message"]


def test_source_crs_reprojects_to_wgs84(client: TestClient) -> None:
    report = upload(client, HEADER + row("Utm", _utm_square()), source_crs="EPSG:32634", dry_run=False).json()
    assert report["accepted"] == 1
    hazard = client.get("/api/hazards/1").json()
    lon, lat = hazard["geometry"]["coordinates"][0][0][0]
    assert abs(lon - 18.0) < 1e-4 and abs(lat - 15.0) < 1e-4
    assert 1.1e6 < hazard["area_m2"] < 1.3e6


def test_unknown_crs_fails_whole_request(client: TestClient) -> None:
    res = upload(client, HEADER + row("A", square_wkt(18, 15)), source_crs="EPSG:nonsense")
    assert res.status_code == 422 and "Unknown source CRS" in res.json()["detail"]


def test_missing_fields_and_bad_enums_are_listed_together(client: TestClient) -> None:
    csv_text = HEADER + f',,XYZ,laser,,,,"{square_wkt(18, 15)}"\n'
    report = upload(client, csv_text).json()
    messages = " | ".join(i["message"] for i in report["rows"][0]["errors"])
    assert "name is required" in messages and "region is required" in messages
    assert "hazard_type 'XYZ'" in messages and "hazard_class 'laser'" in messages


def test_duplicate_within_file_is_rejected(client: TestClient) -> None:
    csv_text = HEADER + row("A", square_wkt(18.0, 15.0)) + row("A copy", square_wkt(18.0, 15.0))
    report = upload(client, csv_text).json()
    assert codes(report, 2) == ["duplicate_in_file"]
    assert report["rows"][0]["outcome"] == "accepted"


def test_duplicate_of_existing_hazard_is_rejected(client: TestClient, hazard: dict) -> None:
    report = upload(client, HEADER + row("Same place", square_wkt(18.0, 15.0))).json()
    assert codes(report, 1) == ["duplicate_existing"]
    assert hazard["code"] in report["rows"][0]["errors"][0]["message"]


def test_partial_overlap_warns_but_accepts(client: TestClient, hazard: dict) -> None:
    report = upload(client, HEADER + row("Shifted", square_wkt(18.005, 15.005))).json()
    assert report["rows"][0]["outcome"] == "accepted"
    assert codes(report, 1, "warnings") == ["overlap"] and report["warning_count"] == 1


def test_reject_overlaps_turns_warning_into_error(client: TestClient, hazard: dict) -> None:
    report = upload(client, HEADER + row("Shifted", square_wkt(18.005, 15.005)), reject_overlaps=True).json()
    assert codes(report, 1) == ["overlap"]


def test_cancelled_hazards_do_not_count_for_overlap(client: TestClient, hazard: dict) -> None:
    client.patch(f"/api/hazards/{hazard['id']}", json={"status": "cancelled"})
    report = upload(client, HEADER + row("Again", square_wkt(18.0, 15.0))).json()
    assert report["rows"][0]["outcome"] == "accepted" and report["warning_count"] == 0


def test_update_by_code_changes_status_and_is_audited(client: TestClient, hazard: dict) -> None:
    csv_text = HEADER + f'{hazard["code"]},,,,confirmed,,,\n'
    report = upload(client, csv_text, dry_run=False).json()
    assert report["updated"] == 1 and report["created"] == 0
    assert client.get(f"/api/hazards/{hazard['id']}").json()["status"] == "confirmed"
    latest = client.get("/api/audit", params={"entity_type": "hazard", "entity_id": hazard["id"]}).json()[0]
    assert latest["changes"] == {"status": ["suspected", "confirmed"]}
    assert latest["source"].startswith("import:")


def test_update_enforces_transition_rules(client: TestClient, hazard: dict) -> None:
    report = upload(client, HEADER + f'{hazard["code"]},,,,released,,,\n').json()
    assert codes(report, 1) == ["invalid_transition"]
    assert "from 'suspected' to 'released'" in report["rows"][0]["errors"][0]["message"]


def test_update_to_released_checks_preconditions(client: TestClient, hazard: dict) -> None:
    client.patch(f"/api/hazards/{hazard['id']}", json={"status": "confirmed"})
    client.patch(f"/api/hazards/{hazard['id']}", json={"status": "in_clearance"})
    report = upload(client, HEADER + f'{hazard["code"]},,,,released,,,\n').json()
    assert "no completed clearance task" in report["rows"][0]["errors"][0]["message"]


def test_unknown_code_and_repeated_code_are_rejected(client: TestClient, hazard: dict) -> None:
    csv_text = HEADER + "KRV-HAZ-99999,,,,confirmed,,,\n" + f'{hazard["code"]},,,,confirmed,,,\n' + f'{hazard["code"]},,,,cancelled,,,\n'
    report = upload(client, csv_text).json()
    assert codes(report, 1) == ["unknown_code"]
    assert report["rows"][1]["outcome"] == "accepted"
    assert codes(report, 3) == ["duplicate_in_file"]


def test_new_hazard_cannot_be_imported_as_released(client: TestClient) -> None:
    report = upload(client, HEADER + row("R", square_wkt(18, 15), status="released")).json()
    assert codes(report, 1) == ["invalid_transition"]


def test_on_error_skip_imports_valid_rows(client: TestClient) -> None:
    csv_text = HEADER + row("Good", square_wkt(18.0, 15.0)) + row("Bad", "POINT(1 1)")
    report = upload(client, csv_text, dry_run=False, on_error="skip").json()
    assert report["committed"] and (report["created"], report["rejected"]) == (1, 1)
    assert len(client.get("/api/hazards").json()) == 1


def test_on_error_abort_imports_nothing(client: TestClient) -> None:
    csv_text = HEADER + row("Good", square_wkt(18.0, 15.0)) + row("Bad", "POINT(1 1)")
    report = upload(client, csv_text, dry_run=False, on_error="abort").json()
    assert report["committed"] is False and report["rejected"] == 1
    assert client.get("/api/hazards").json() == []


def test_geojson_upload(client: TestClient) -> None:
    doc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "G1", "hazard_type": "cha", "hazard_class": "Anti Vehicle",
                               "region": "River Delta", "status": "Confirmed"},
                "geometry": {"type": "Polygon", "coordinates": [[[18, 15], [18.01, 15], [18.01, 15.01], [18, 15.01], [18, 15]]]},
            },
            {"type": "Feature", "properties": {"name": "NoGeom"}, "geometry": None},
        ],
    }
    res = client.post(URL, files={"file": ("h.geojson", json.dumps(doc), "application/json")},
                      data={"dry_run": "false"})
    report = res.json()
    assert (report["created"], report["rejected"]) == (1, 1)
    h = client.get("/api/hazards/1").json()
    assert (h["hazard_type"], h["hazard_class"], h["status"]) == ("CHA", "anti_vehicle", "confirmed")
    assert "geometry is required" in " ".join(i["message"] for i in report["rows"][1]["errors"])


def test_unusable_files_return_422(client: TestClient) -> None:
    assert client.post(URL, files={"file": ("h.txt", "x", "text/plain")}).status_code == 422
    assert upload(client, "name,region\nA,B\n").status_code == 422  # no geometry column
    assert upload(client, HEADER).status_code == 422  # no rows
    bad = client.post(URL, files={"file": ("h.geojson", "{not json", "application/json")})
    assert bad.status_code == 422
