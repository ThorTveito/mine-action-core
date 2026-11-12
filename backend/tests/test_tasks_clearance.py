from fastapi.testclient import TestClient


def _task(client: TestClient, hazard_id: int, **extra: object) -> dict:
    payload = {"hazard_id": hazard_id, "task_type": "clearance", "organisation": "Org", **extra}
    res = client.post("/api/tasks", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_task_generates_code_and_defaults(client: TestClient, hazard: dict) -> None:
    task = _task(client, hazard["id"])
    assert task["code"] == "KRV-TSK-00001"
    assert task["status"] == "planned"


def test_create_task_for_missing_hazard_is_404(client: TestClient) -> None:
    res = client.post(
        "/api/tasks", json={"hazard_id": 42, "task_type": "survey", "organisation": "Org"}
    )
    assert res.status_code == 404


def test_task_rejects_end_before_start(client: TestClient, hazard: dict) -> None:
    res = client.post(
        "/api/tasks",
        json={
            "hazard_id": hazard["id"],
            "task_type": "survey",
            "organisation": "Org",
            "planned_start": "2026-03-10",
            "planned_end": "2026-03-01",
        },
    )
    assert res.status_code == 422


def test_task_filters(client: TestClient, hazard: dict) -> None:
    _task(client, hazard["id"], task_type="survey")
    _task(client, hazard["id"], task_type="clearance", status="active")
    assert len(client.get("/api/tasks", params={"hazard_id": hazard["id"]}).json()) == 2
    active = client.get("/api/tasks", params={"status": "active"}).json()
    assert [t["task_type"] for t in active] == ["clearance"]


def test_patch_task_and_validations(client: TestClient, hazard: dict) -> None:
    task = _task(client, hazard["id"], planned_start="2026-03-01", planned_end="2026-03-10")
    url = f"/api/tasks/{task['id']}"
    assert client.patch(url, json={"status": "active"}).json()["status"] == "active"
    assert client.patch(url, json={"status": None}).status_code == 422
    assert client.patch(url, json={"planned_end": "2026-02-01"}).status_code == 422
    assert client.patch("/api/tasks/9999", json={"status": "active"}).status_code == 404


def test_delete_task(client: TestClient, hazard: dict) -> None:
    task = _task(client, hazard["id"])
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 204
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 404


def test_clearance_record_happy_path_and_filter(client: TestClient, hazard: dict) -> None:
    task = _task(client, hazard["id"])
    body = {
        "task_id": task["id"],
        "record_date": "2026-02-01",
        "area_cleared_m2": 120.5,
        "items_found": 2,
        "items_destroyed": 1,
        "team": "Team Bravo",
    }
    created = client.post("/api/clearance-records", json=body)
    assert created.status_code == 201
    listed = client.get("/api/clearance-records", params={"task_id": task["id"]}).json()
    assert [r["area_cleared_m2"] for r in listed] == [120.5]
    assert client.get(f"/api/clearance-records/{created.json()['id']}").status_code == 200


def test_clearance_record_validation(client: TestClient, hazard: dict) -> None:
    task = _task(client, hazard["id"])
    base = {"task_id": task["id"], "record_date": "2026-02-01", "team": "Team Bravo"}
    assert client.post("/api/clearance-records", json={**base, "area_cleared_m2": -1}).status_code == 422
    over = {**base, "items_found": 1, "items_destroyed": 2}
    assert client.post("/api/clearance-records", json=over).status_code == 422
    missing = {**base, "task_id": 999}
    assert client.post("/api/clearance-records", json=missing).status_code == 404


def test_clearance_record_not_found_and_delete(client: TestClient, hazard: dict) -> None:
    assert client.get("/api/clearance-records/9999").status_code == 404
    task = _task(client, hazard["id"])
    rec = client.post(
        "/api/clearance-records",
        json={"task_id": task["id"], "record_date": "2026-02-01", "team": "T"},
    ).json()
    assert client.delete(f"/api/clearance-records/{rec['id']}").status_code == 204
    assert client.delete(f"/api/clearance-records/{rec['id']}").status_code == 404
