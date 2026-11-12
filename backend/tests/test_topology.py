from fastapi.testclient import TestClient
from shapely.geometry import MultiPolygon, Polygon, box

from app import topology
from tests.helpers import box_geojson, make_hazard, prepare_for_release, square_wkt

# 0.001 degrees is about 107 m of longitude / 111 m of latitude near lat 15.
A = box_geojson(18.000, 15.000, 18.004, 15.004)


def check(client: TestClient, **params: object) -> dict:
    res = client.get("/api/topology/check", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def rules(report: dict) -> list[str]:
    return [i["rule"] for i in report["issues"]]


# --------------------------------------------------------------- between polygons


def test_separated_hazards_have_no_issues(client: TestClient) -> None:
    make_hazard(client, A)
    make_hazard(client, box_geojson(18.1, 15.0, 18.104, 15.004))
    report = check(client)
    assert report["checked_hazards"] == 2 and report["issues"] == []


def test_overlap_is_an_error_with_location_and_area(client: TestClient) -> None:
    a = make_hazard(client, A)
    b = make_hazard(client, box_geojson(18.002, 15.002, 18.006, 15.006))
    issue = check(client)["issues"][0]
    assert issue["rule"] == "overlap" and issue["severity"] == "error"
    assert issue["hazard_ids"] == [a["id"], b["id"]]
    assert 40_000 < issue["value"] < 55_000  # about 214 m x 222 m
    lon, lat = issue["location"]["coordinates"]
    assert 18.002 <= lon <= 18.004 and 15.002 <= lat <= 15.004


def test_touching_edges_are_not_an_overlap(client: TestClient) -> None:
    make_hazard(client, A)
    make_hazard(client, box_geojson(18.004, 15.000, 18.008, 15.004))
    assert check(client)["issues"] == []


def test_tiny_overlap_is_only_a_warning(client: TestClient) -> None:
    make_hazard(client, A)
    make_hazard(client, box_geojson(18.00399, 15.00395, 18.008, 15.008))  # about 6 m2 shared
    issue = check(client)["issues"][0]
    assert (issue["rule"], issue["severity"]) == ("minor_overlap", "warning")


def test_release_conflict_when_a_new_hazard_overlaps_a_released_one(client: TestClient) -> None:
    from tests.helpers import release_hazard

    released = make_hazard(client, A)
    release_hazard(client, released["id"])
    make_hazard(client, box_geojson(18.002, 15.0, 18.006, 15.004))
    issue = check(client)["issues"][0]
    assert issue["rule"] == "release_conflict" and issue["severity"] == "error"


def test_near_miss_gap_is_reported_within_tolerance(client: TestClient) -> None:
    make_hazard(client, A)
    make_hazard(client, box_geojson(18.00401, 15.0, 18.008, 15.004))  # about 1.07 m away
    issue = check(client)["issues"][0]
    assert issue["rule"] == "gap" and 0.9 < issue["value"] < 1.3


def test_gap_tolerance_is_configurable(client: TestClient) -> None:
    make_hazard(client, A)
    make_hazard(client, box_geojson(18.00403, 15.0, 18.008, 15.004))  # about 3.2 m away
    assert check(client)["issues"] == []
    assert rules(check(client, gap_tolerance_m=5)) == ["gap"]


def test_cancelled_hazards_are_ignored(client: TestClient) -> None:
    make_hazard(client, A)
    ghost = make_hazard(client, box_geojson(18.002, 15.002, 18.006, 15.006))
    client.patch(f"/api/hazards/{ghost['id']}", json={"status": "cancelled"})
    report = check(client)
    assert report["checked_hazards"] == 1 and report["issues"] == []


# ----------------------------------------------------------------- within a polygon


def test_sliver_tiny_area_spike_and_tiny_hole_are_flagged(client: TestClient) -> None:
    make_hazard(client, box_geojson(18.0, 15.0, 18.00004, 15.01))  # 4 m wide, 1.1 km long
    make_hazard(client, box_geojson(18.1, 15.0, 18.10002, 15.00002))  # 2 m square
    needle = {
        "type": "Polygon",
        "coordinates": [[[18.2, 15.0], [18.204, 15.0], [18.204, 15.004], [18.2021, 15.004],
                         [18.20205, 15.010], [18.2019, 15.004], [18.2, 15.004], [18.2, 15.0]]],
    }  # fmt: skip
    make_hazard(client, needle)
    holey = {
        "type": "Polygon",
        "coordinates": [
            [[18.3, 15.0], [18.304, 15.0], [18.304, 15.004], [18.3, 15.004], [18.3, 15.0]],
            [[18.301, 15.001], [18.30102, 15.001], [18.30102, 15.00102], [18.301, 15.00102], [18.301, 15.001]],
        ],
    }  # fmt: skip
    make_hazard(client, holey)
    found = set(rules(check(client)))
    assert {"sliver", "tiny_area", "spike", "tiny_hole"} <= found
    assert all(i["severity"] == "warning" for i in check(client)["issues"])


def test_geometry_issues_unit() -> None:
    clean = box(18.0, 15.0, 18.004, 15.004)
    assert topology.geometry_issues(clean, 98_000, 1_100) == []
    assert topology.compactness(98_000, 1_100) > 0.9  # close to a square
    assert topology.compactness(0, 0) == 0
    findings = topology.geometry_issues(MultiPolygon([clean]), 10.0, 14.0)
    assert [f.rule for f in findings] == ["tiny_area"]


def test_duplicate_vertices_are_info() -> None:
    poly = Polygon([(18, 15), (18.004, 15), (18.004, 15), (18.004, 15.004), (18, 15.004)])
    findings = topology.geometry_issues(poly, 98_000, 1_100)
    assert [(f.rule, f.severity) for f in findings] == [("duplicate_vertices", "info")]


# --------------------------------------------------------------------------- API


def test_check_filters_by_hazard_and_severity(client: TestClient) -> None:
    a = make_hazard(client, A)
    make_hazard(client, box_geojson(18.002, 15.002, 18.006, 15.006))
    far = make_hazard(client, box_geojson(18.5, 15.0, 18.50002, 15.00002))  # tiny
    assert rules(check(client, hazard_id=a["id"])) == ["overlap"]
    assert rules(check(client, hazard_id=far["id"])) == ["tiny_area"]
    assert rules(check(client, min_severity="error")) == ["overlap"]
    assert check(client)["by_severity"] == {"error": 1, "warning": 1}
    assert client.get("/api/topology/check", params={"hazard_id": 9999}).status_code == 404
    assert client.get("/api/topology/check", params={"gap_tolerance_m": 500}).status_code == 422


def test_topology_errors_block_release(client: TestClient) -> None:
    a = make_hazard(client, A)
    make_hazard(client, box_geojson(18.002, 15.002, 18.006, 15.006))
    prepare_for_release(client, a["id"])
    res = client.patch(f"/api/hazards/{a['id']}", json={"status": "released"})
    assert res.status_code == 409
    assert "topology errors must be fixed first" in res.json()["detail"]


def test_topology_warnings_do_not_block_release(client: TestClient) -> None:
    sliver = make_hazard(client, box_geojson(18.0, 15.0, 18.00004, 15.01))
    prepare_for_release(client, sliver["id"])
    assert client.patch(f"/api/hazards/{sliver['id']}", json={"status": "released"}).status_code == 200


def test_adjacency_and_clusters(client: TestClient) -> None:
    a = make_hazard(client, box_geojson(18.000, 15.000, 18.004, 15.004))
    b = make_hazard(client, box_geojson(18.004, 15.000, 18.008, 15.004))  # shares an edge with a
    c = make_hazard(client, box_geojson(18.000, 15.004, 18.004, 15.008))  # shares an edge with a
    make_hazard(client, box_geojson(18.5, 15.0, 18.504, 15.004))  # isolated

    edges = client.get("/api/topology/adjacency").json()
    assert {(e["a_id"], e["b_id"]) for e in edges} == {(a["id"], b["id"]), (a["id"], c["id"])}
    assert all(400 < e["shared_boundary_m"] < 500 for e in edges)

    body = client.get("/api/topology/clusters").json()
    assert (body["cluster_count"], body["clustered_hazards"], body["isolated_hazards"]) == (1, 3, 1)
    cluster = body["clusters"][0]
    assert cluster["hazard_count"] == 3 and cluster["regions"] == ["Central Basin"]
    assert {m["id"] for m in cluster["members"]} == {a["id"], b["id"], c["id"]}
    assert client.get("/api/topology/clusters", params={"min_size": 4}).json()["cluster_count"] == 0


def test_overlapping_hazards_are_not_adjacent(client: TestClient) -> None:
    make_hazard(client, A)
    make_hazard(client, box_geojson(18.002, 15.0, 18.006, 15.004))
    assert client.get("/api/topology/adjacency").json() == []


# -------------------------------------------------------------- import integration

CSV_HEADER = "code,name,hazard_type,hazard_class,status,region,description,wkt\n"


def _upload(client: TestClient, wkt: str):
    line = f',Row,SHA,mixed,,Central Basin,,"{wkt}"\n'
    return client.post(
        "/api/imports/hazards", files={"file": ("h.csv", CSV_HEADER + line, "text/csv")}
    ).json()


def test_import_warns_about_sliver_and_near_miss(client: TestClient) -> None:
    make_hazard(client, A)
    report = _upload(client, "POLYGON((18.00401 15.0, 18.00403 15.0, 18.00403 15.004, 18.00401 15.004, 18.00401 15.0))")
    row = report["rows"][0]
    assert row["outcome"] == "accepted"
    assert {w["code"] for w in row["warnings"]} == {"topology_sliver", "topology_gap"}


def test_import_warns_about_tiny_area(client: TestClient) -> None:
    report = _upload(client, square_wkt(18.5, 15.0, 0.00002))
    assert [w["code"] for w in report["rows"][0]["warnings"]] == ["topology_tiny_area"]
