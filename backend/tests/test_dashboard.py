import pytest
from fastapi.testclient import TestClient

from tests.helpers import release_hazard


def test_dashboard_empty(client: TestClient) -> None:
    body = client.get("/api/dashboard").json()
    assert body["release_percent"] == 0
    assert body["by_region"] == []
    assert body["monthly_clearance"] == []


def test_dashboard_progress_by_region_and_month(
    client: TestClient, hazard: dict, hazard_payload: dict
) -> None:
    far = {
        "type": "Polygon",
        "coordinates": [[[18.5, 15.0], [18.51, 15.0], [18.51, 15.01], [18.5, 15.01], [18.5, 15.0]]],
    }
    other = client.post(
        "/api/hazards", json={**hazard_payload, "region": "River Delta", "geometry": far}
    ).json()
    release_hazard(client, hazard["id"], cleared=800, found=2)

    body = client.get("/api/dashboard").json()
    total = hazard["area_m2"] + other["area_m2"]
    assert body["contaminated_area_m2"] == pytest.approx(total)
    assert body["released_area_m2"] == pytest.approx(hazard["area_m2"])
    assert body["remaining_area_m2"] == pytest.approx(other["area_m2"])
    assert body["release_percent"] == pytest.approx(50, abs=0.2)
    assert body["tasks_by_status"]["completed"] == 1

    regions = {r["region"]: r for r in body["by_region"]}
    assert regions["Central Basin"]["released_area_m2"] == pytest.approx(hazard["area_m2"])
    assert regions["Central Basin"]["cleared_area_m2"] == 800
    assert regions["River Delta"]["remaining_area_m2"] == pytest.approx(other["area_m2"])
    assert body["monthly_clearance"] == [
        {"month": "2026-01", "cleared_area_m2": 800, "items_destroyed": 2, "items_found": 2}
    ]


def test_cancelled_area_is_excluded_from_contaminated(client: TestClient, hazard: dict) -> None:
    client.patch(f"/api/hazards/{hazard['id']}", json={"status": "cancelled"})
    body = client.get("/api/dashboard").json()
    assert body["contaminated_area_m2"] == 0
    assert body["cancelled_area_m2"] == pytest.approx(hazard["area_m2"])


# ------------------------------------------------------------------ fuller dashboard


def _field_reports_and_qa(client: TestClient, as_role) -> None:
    surveyor = as_role("surveyor")
    base = {
        "observed_at": "2026-01-01T10:00:00Z",
        "finding_type": "suspected_area",
        "lon": 18.3,
        "lat": 15.3,
        "description": "Informant Jane Doe says the hill is mined",
    }
    first = surveyor.post("/api/field-reports", json={**base, "client_id": "dash-0001"}).json()
    surveyor.post("/api/field-reports", json={**base, "client_id": "dash-0002"})
    client.post(f"/api/field-reports/{first['id']}/reject", json={"reason": "duplicate"})


def test_dashboard_sections(
    client: TestClient, hazard: dict, hazard_payload: dict, as_role
) -> None:
    far = {
        "type": "Polygon",
        "coordinates": [[[18.5, 15.0], [18.51, 15.0], [18.51, 15.01], [18.5, 15.01], [18.5, 15.0]]],
    }
    other = client.post(
        "/api/hazards",
        json={**hazard_payload, "region": "River Delta", "geometry": far, "hazard_class": "uxo"},
    ).json()
    release_hazard(client, hazard["id"], cleared=800, found=2)
    _field_reports_and_qa(client, as_role)

    body = client.get("/api/dashboard").json()
    assert body["regions"] == ["Central Basin", "River Delta"] and body["region"] is None
    assert (body["hazard_count"], body["open_hazard_count"]) == (2, 1)
    assert (body["items_found"], body["items_destroyed"]) == (2, 2)
    assert body["hazards_by_status"]["released"] == 1
    assert {c["hazard_class"] for c in body["hazards_by_class"]} == {"anti_personnel", "uxo"}
    assert body["tasks_by_type"]["clearance"] == 1
    assert body["monthly_clearance"][0]["items_found"] == 2
    org = body["organisations"][0]
    assert (org["organisation"], org["completed_tasks"], org["cleared_area_m2"]) == ("Org", 1, 800)
    assert body["qa"] == {
        "inspections": 1,
        "passed": 1,
        "failed": 0,
        "pass_rate": 100.0,
        "residual_items": 0,
    }
    fr = body["field_reports"]
    assert (
        fr["total"] == 2
        and fr["by_status"]["rejected"] == 1
        and fr["by_finding_type"]["suspected_area"] == 2
    )
    assert fr["median_review_hours"] is not None
    assert body["data_quality"] == {"errors": 0, "warnings": 0, "by_rule": {}}
    summaries = [a["summary"] for a in body["recent_activity"]]
    assert "KRV-HAZ-00001: in clearance → released" in summaries
    assert other["code"] + " registered (suspected)" in summaries
    assert all(a["entity_type"] != "field_report" for a in body["recent_activity"])


def test_dashboard_region_filter(client: TestClient, hazard: dict, hazard_payload: dict) -> None:
    far = {
        "type": "Polygon",
        "coordinates": [[[18.5, 15.0], [18.51, 15.0], [18.51, 15.01], [18.5, 15.01], [18.5, 15.0]]],
    }
    other = client.post(
        "/api/hazards", json={**hazard_payload, "region": "River Delta", "geometry": far}
    ).json()
    release_hazard(client, hazard["id"], cleared=800)

    delta = client.get("/api/dashboard", params={"region": "River Delta"}).json()
    assert delta["region"] == "River Delta" and delta["regions"] == ["Central Basin", "River Delta"]
    assert delta["hazard_count"] == 1 and delta["contaminated_area_m2"] == pytest.approx(
        other["area_m2"]
    )
    assert delta["release_percent"] == 0 and delta["monthly_clearance"] == []
    assert delta["qa"]["inspections"] == 0 and delta["qa"]["pass_rate"] is None
    assert [r["region"] for r in delta["by_region"]] == ["River Delta"]
    assert delta["organisations"] == []
    basin = client.get("/api/dashboard", params={"region": "Central Basin"}).json()
    assert basin["release_percent"] == 100 and basin["qa"]["passed"] == 1
    assert client.get("/api/dashboard", params={"region": "Atlantis"}).status_code == 404


def test_dashboard_is_public_and_leaks_nothing_private(
    anon: TestClient, client: TestClient, as_role
) -> None:
    _field_reports_and_qa(client, as_role)
    text = anon.get("/api/dashboard").text
    assert "Jane Doe" not in text and "surveyor" not in text and "admin" not in text
