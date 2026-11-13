"""Land release (IMAS 07.11): cancelled by NTS, reduced by TS, cleared by clearance."""

import pytest
from fastapi.testclient import TestClient

from tests.helpers import box_geojson, make_hazard

BOX = box_geojson(18.0, 15.0, 18.004, 15.004)  # about 0.19 km2


def task(client: TestClient, hazard_id: int, task_type: str, status: str = "active") -> dict:
    res = client.post(
        "/api/tasks",
        json={
            "hazard_id": hazard_id,
            "task_type": task_type,
            "organisation": "Org",
            "status": status,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def record(client: TestClient, task_id: int, area: float, **extra: object):
    return client.post(
        "/api/clearance-records",
        json={
            "task_id": task_id,
            "record_date": "2026-03-01",
            "area_cleared_m2": area,
            "team": "T",
            **extra,
        },
    )


@pytest.mark.parametrize(
    "task_type,method",
    [("survey", "cancelled"), ("technical_survey", "reduced"), ("clearance", "cleared")],
)
def test_release_method_follows_the_task_type(
    client: TestClient, task_type: str, method: str
) -> None:
    hazard = make_hazard(client, BOX)
    res = record(client, task(client, hazard["id"], task_type)["id"], 100)
    assert res.status_code == 201 and res.json()["release_method"] == method


def test_inconsistent_method_and_verification_are_refused(client: TestClient) -> None:
    hazard = make_hazard(client, BOX)
    ts = task(client, hazard["id"], "technical_survey")
    res = record(client, ts["id"], 100, release_method="cleared")
    assert res.status_code == 422 and "releases land as 'reduced'" in res.json()["detail"]
    verification = task(client, hazard["id"], "verification")
    res = record(client, verification["id"], 100)
    assert res.status_code == 422 and "do not release land" in res.json()["detail"]


def test_cannot_release_more_than_the_hazard(client: TestClient) -> None:
    hazard = make_hazard(client, BOX)
    t = task(client, hazard["id"], "clearance")
    assert record(client, t["id"], hazard["area_m2"] * 0.6).status_code == 201
    res = record(client, t["id"], hazard["area_m2"] * 0.5)
    assert res.status_code == 422 and "more than KRV-HAZ-00001" in res.json()["detail"]


def test_dashboard_reports_release_by_method_and_outstanding_area(client: TestClient) -> None:
    hazard = make_hazard(client, BOX)
    record(client, task(client, hazard["id"], "technical_survey")["id"], 30_000)
    record(
        client,
        task(client, hazard["id"], "clearance")["id"],
        20_000,
        items_found=3,
        items_destroyed=3,
    )
    body = client.get("/api/dashboard").json()
    release = body["land_release"]
    assert (release["reduced_m2"], release["cleared_m2"], release["cancelled_m2"]) == (
        30_000,
        20_000,
        0,
    )
    assert release["total_m2"] == 50_000 and release["items_destroyed"] == 3
    assert release["by_year"] == [
        {"year": 2026, "cancelled": 0, "reduced": 30_000, "cleared": 20_000, "items_destroyed": 3}
    ]
    assert body["outstanding_area_m2"] == pytest.approx(hazard["area_m2"] - 50_000)


def test_technical_survey_alone_can_lead_to_release(client: TestClient) -> None:
    hazard = make_hazard(client, BOX)
    url = f"/api/hazards/{hazard['id']}"
    client.patch(url, json={"status": "confirmed"})
    ts = task(client, hazard["id"], "technical_survey")
    client.patch(url, json={"status": "in_clearance"})
    record(client, ts["id"], hazard["area_m2"])
    client.patch(f"/api/tasks/{ts['id']}", json={"status": "completed"})
    assert (
        "technical_survey task" in client.patch(url, json={"status": "released"}).json()["detail"]
    )
    qa = client.post(
        "/api/qa-inspections",
        json={"task_id": ts["id"], "inspection_date": "2026-03-05", "outcome": "pass"},
    )
    assert qa.status_code == 201
    assert client.patch(url, json={"status": "released"}).status_code == 200
