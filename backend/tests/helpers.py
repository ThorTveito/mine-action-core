from fastapi.testclient import TestClient


def square_wkt(lon: float, lat: float, size: float = 0.01) -> str:
    x2, y2 = lon + size, lat + size
    return f"POLYGON(({lon} {lat}, {x2} {lat}, {x2} {y2}, {lon} {y2}, {lon} {lat}))"


def box_geojson(x1: float, y1: float, x2: float, y2: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]],
    }


def make_hazard(client: TestClient, geometry: dict, **extra: object) -> dict:
    payload = {
        "name": "H",
        "hazard_type": "SHA",
        "hazard_class": "mixed",
        "region": "Central Basin",
        "geometry": geometry,
        **extra,
    }
    res = client.post("/api/hazards", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def prepare_for_release(
    client: TestClient, hazard_id: int, cleared: float = 100, found: int = 0
) -> dict:
    """Everything a hazard needs before release: clearance, a completed task, passing QA."""
    url = f"/api/hazards/{hazard_id}"
    assert client.patch(url, json={"status": "confirmed"}).status_code == 200
    task = client.post(
        "/api/tasks",
        json={"hazard_id": hazard_id, "task_type": "clearance", "organisation": "Org"},
    ).json()
    assert client.patch(url, json={"status": "in_clearance"}).status_code == 200
    client.post(
        "/api/clearance-records",
        json={
            "task_id": task["id"],
            "record_date": "2026-01-05",
            "area_cleared_m2": cleared,
            "items_found": found,
            "items_destroyed": found,
            "team": "Team Alpha",
        },
    )
    assert client.patch(f"/api/tasks/{task['id']}", json={"status": "completed"}).status_code == 200
    qa = client.post(
        "/api/qa-inspections",
        json={
            "task_id": task["id"],
            "inspection_date": "2026-01-10",
            "sample_area_m2": 10,
            "outcome": "pass",
        },
    )
    assert qa.status_code == 201, qa.text
    return task


def release_hazard(client: TestClient, hazard_id: int, cleared: float = 100, found: int = 0) -> None:
    """Walk a hazard through the legal lifecycle to `released` (use an admin client)."""
    prepare_for_release(client, hazard_id, cleared, found)
    res = client.patch(f"/api/hazards/{hazard_id}", json={"status": "released"})
    assert res.status_code == 200, res.text
