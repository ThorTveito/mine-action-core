from fastapi.testclient import TestClient


def square_wkt(lon: float, lat: float, size: float = 0.01) -> str:
    x2, y2 = lon + size, lat + size
    return f"POLYGON(({lon} {lat}, {x2} {lat}, {x2} {y2}, {lon} {y2}, {lon} {lat}))"


def release_hazard(client: TestClient, hazard_id: int, cleared: float = 100, found: int = 0) -> None:
    """Walk a hazard through the legal lifecycle to `released`."""
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
    res = client.patch(url, json={"status": "released"})
    assert res.status_code == 200, res.text
