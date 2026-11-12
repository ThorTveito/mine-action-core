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
    other = client.post("/api/hazards", json={**hazard_payload, "region": "River Delta"}).json()
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
        {"month": "2026-01", "cleared_area_m2": 800, "items_destroyed": 2}
    ]


def test_cancelled_area_is_excluded_from_contaminated(client: TestClient, hazard: dict) -> None:
    client.patch(f"/api/hazards/{hazard['id']}", json={"status": "cancelled"})
    body = client.get("/api/dashboard").json()
    assert body["contaminated_area_m2"] == 0
    assert body["cancelled_area_m2"] == pytest.approx(hazard["area_m2"])
