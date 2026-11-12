from fastapi.testclient import TestClient

BIGGER = {
    "type": "Polygon",
    "coordinates": [[[18.0, 15.0], [18.02, 15.0], [18.02, 15.02], [18.0, 15.02], [18.0, 15.0]]],
}


def _audit(client: TestClient, **params: object) -> list[dict]:
    return client.get("/api/audit", params=params).json()


def test_create_is_audited(client: TestClient, hazard: dict) -> None:
    entries = _audit(client, entity_type="hazard", entity_id=hazard["id"])
    assert len(entries) == 1
    entry = entries[0]
    assert entry["action"] == "create"
    assert entry["source"] == "api"
    assert entry["changes"]["code"] == [None, "KRV-HAZ-00001"]
    assert entry["changes"]["status"] == [None, "suspected"]


def test_update_records_old_and_new_values(client: TestClient, hazard: dict) -> None:
    client.patch(f"/api/hazards/{hazard['id']}", json={"status": "confirmed", "name": "Renamed"})
    latest = _audit(client, entity_type="hazard", entity_id=hazard["id"])[0]
    assert latest["action"] == "update"
    assert latest["changes"] == {
        "status": ["suspected", "confirmed"],
        "name": ["Test Field", "Renamed"],
    }


def test_noop_update_writes_no_audit_row(client: TestClient, hazard: dict) -> None:
    client.patch(f"/api/hazards/{hazard['id']}", json={"name": "Test Field"})
    assert len(_audit(client, entity_type="hazard", entity_id=hazard["id"])) == 1


def test_geometry_change_is_flagged_with_area(client: TestClient, hazard: dict) -> None:
    client.patch(f"/api/hazards/{hazard['id']}", json={"geometry": BIGGER})
    changes = _audit(client, entity_type="hazard", entity_id=hazard["id"])[0]["changes"]
    assert "geometry" in changes
    assert changes["area_m2"][0] < changes["area_m2"][1]


def test_rejected_change_is_not_audited(client: TestClient, hazard: dict) -> None:
    client.patch(f"/api/hazards/{hazard['id']}", json={"status": "released"})
    assert len(_audit(client, entity_type="hazard", entity_id=hazard["id"])) == 1


def test_delete_survives_in_audit_log(client: TestClient, hazard: dict) -> None:
    client.delete(f"/api/hazards/{hazard['id']}")
    entries = _audit(client, entity_type="hazard", entity_id=hazard["id"])
    assert [e["action"] for e in entries] == ["delete", "create"]


def test_task_and_record_changes_are_audited(client: TestClient, hazard: dict) -> None:
    task = client.post(
        "/api/tasks",
        json={"hazard_id": hazard["id"], "task_type": "survey", "organisation": "Org"},
    ).json()
    client.patch(f"/api/tasks/{task['id']}", json={"status": "active"})
    rec = client.post(
        "/api/clearance-records",
        json={"task_id": task["id"], "record_date": "2026-02-01", "team": "T"},
    ).json()
    tasks = _audit(client, entity_type="task", entity_id=task["id"])
    assert [e["action"] for e in tasks] == ["update", "create"]
    assert tasks[0]["changes"] == {"status": ["planned", "active"]}
    assert _audit(client, entity_type="clearance_record", entity_id=rec["id"])[0]["action"] == "create"
