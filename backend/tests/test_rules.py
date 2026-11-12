from fastapi.testclient import TestClient

from tests.helpers import release_hazard


def _patch(client: TestClient, hazard_id: int, status: str):
    return client.patch(f"/api/hazards/{hazard_id}", json={"status": status})


def test_new_hazard_cannot_start_released(client: TestClient, hazard_payload: dict) -> None:
    hazard_payload["status"] = "released"
    res = client.post("/api/hazards", json=hazard_payload)
    assert res.status_code == 422
    assert "cannot start as 'released'" in res.json()["detail"]


def test_illegal_transition_is_conflict(client: TestClient, hazard: dict) -> None:
    res = _patch(client, hazard["id"], "released")
    assert res.status_code == 409
    assert "from 'suspected' to 'released'" in res.json()["detail"]
    assert _patch(client, hazard["id"], "in_clearance").status_code == 409


def test_same_status_patch_is_allowed(client: TestClient, hazard: dict) -> None:
    assert _patch(client, hazard["id"], "suspected").status_code == 200


def test_cannot_release_without_completed_clearance(client: TestClient, hazard: dict) -> None:
    _patch(client, hazard["id"], "confirmed")
    _patch(client, hazard["id"], "in_clearance")
    res = _patch(client, hazard["id"], "released")
    assert res.status_code == 409
    assert "no completed clearance task" in res.json()["detail"]


def test_cannot_release_with_open_task(client: TestClient, hazard: dict) -> None:
    release_hazard_prereqs = client.post(
        "/api/tasks",
        json={
            "hazard_id": hazard["id"],
            "task_type": "clearance",
            "organisation": "Org",
            "status": "completed",
        },
    )
    assert release_hazard_prereqs.status_code == 201
    client.post(
        "/api/tasks",
        json={"hazard_id": hazard["id"], "task_type": "verification", "organisation": "Org"},
    )
    _patch(client, hazard["id"], "confirmed")
    _patch(client, hazard["id"], "in_clearance")
    res = _patch(client, hazard["id"], "released")
    assert res.status_code == 409
    assert "still planned, active or suspended" in res.json()["detail"]


def test_full_lifecycle_then_terminal(client: TestClient, hazard: dict) -> None:
    release_hazard(client, hazard["id"])
    res = _patch(client, hazard["id"], "confirmed")
    assert res.status_code == 409
    assert "none (terminal)" in res.json()["detail"]


def test_in_clearance_can_fall_back_to_confirmed(client: TestClient, hazard: dict) -> None:
    _patch(client, hazard["id"], "confirmed")
    _patch(client, hazard["id"], "in_clearance")
    assert _patch(client, hazard["id"], "confirmed").status_code == 200
