from fastapi.testclient import TestClient

from tests.helpers import box_geojson, make_hazard, prepare_for_release

SQUARE = box_geojson(18.0, 15.0, 18.01, 15.01)


def _clearance_task(client: TestClient, hazard_id: int, status: str = "active") -> dict:
    res = client.post(
        "/api/tasks",
        json={"hazard_id": hazard_id, "task_type": "clearance", "organisation": "O", "status": status},
    )
    assert res.status_code == 201
    return res.json()


def _inspect(client: TestClient, task_id: int, outcome: str = "pass", day: str = "2026-02-01", **extra):
    return client.post(
        "/api/qa-inspections",
        json={"task_id": task_id, "inspection_date": day, "outcome": outcome, **extra},
    )


def test_create_inspection_records_inspector(as_role, client: TestClient) -> None:
    task = _clearance_task(client, make_hazard(client, SQUARE)["id"])
    res = _inspect(as_role("qa_officer"), task["id"], sample_area_m2=50)
    assert res.status_code == 201
    body = res.json()
    assert body["inspector"] == "qa_officer" and body["inspection_type"] == "qa"
    entry = client.get("/api/audit", params={"entity_type": "qa_inspection"}).json()[0]
    assert entry["actor"] == "qa_officer" and entry["action"] == "create"


def test_pass_with_residual_items_is_invalid(client: TestClient) -> None:
    task = _clearance_task(client, make_hazard(client, SQUARE)["id"])
    res = _inspect(client, task["id"], "pass", residual_items_found=1)
    assert res.status_code == 422
    assert _inspect(client, task["id"], "fail", residual_items_found=1).status_code == 201


def test_only_active_or_completed_clearance_tasks_can_be_inspected(client: TestClient) -> None:
    hid = make_hazard(client, SQUARE)["id"]
    survey = client.post(
        "/api/tasks", json={"hazard_id": hid, "task_type": "survey", "organisation": "O", "status": "active"}
    ).json()
    planned = _clearance_task(client, hid, "planned")
    assert "Only clearance tasks" in _inspect(client, survey["id"]).json()["detail"]
    assert "only active or completed" in _inspect(client, planned["id"]).json()["detail"]
    assert _inspect(client, 9999).status_code == 404


def test_list_get_filter_and_delete(as_role, client: TestClient) -> None:
    hid = make_hazard(client, SQUARE)["id"]
    t1, t2 = _clearance_task(client, hid), _clearance_task(client, hid)
    first = _inspect(client, t1["id"], day="2026-02-01").json()
    _inspect(client, t1["id"], day="2026-03-01")
    _inspect(client, t2["id"])
    listed = client.get("/api/qa-inspections", params={"task_id": t1["id"]}).json()
    assert [i["inspection_date"] for i in listed] == ["2026-03-01", "2026-02-01"]  # newest first
    assert client.get(f"/api/qa-inspections/{first['id']}").status_code == 200
    assert client.get("/api/qa-inspections/9999").status_code == 404
    assert as_role("qa_officer").delete(f"/api/qa-inspections/{first['id']}").status_code == 403
    assert client.delete(f"/api/qa-inspections/{first['id']}").status_code == 204
    assert client.delete(f"/api/qa-inspections/{first['id']}").status_code == 404


def test_release_needs_a_qa_inspection(client: TestClient) -> None:
    hid = make_hazard(client, SQUARE)["id"]
    url = f"/api/hazards/{hid}"
    client.patch(url, json={"status": "confirmed"})
    task = _clearance_task(client, hid, "completed")
    client.patch(url, json={"status": "in_clearance"})
    res = client.patch(url, json={"status": "released"})
    assert res.status_code == 409 and f"{task['code']} has no QA inspection" in res.json()["detail"]


def test_failed_inspection_blocks_release_until_a_later_pass(client: TestClient) -> None:
    hid = make_hazard(client, SQUARE)["id"]
    task = prepare_for_release(client, hid)  # includes a passing inspection on 2026-01-10
    _inspect(client, task["id"], "fail", day="2026-01-20", residual_items_found=2)
    res = client.patch(f"/api/hazards/{hid}", json={"status": "released"})
    assert res.status_code == 409 and "failed (2026-01-20)" in res.json()["detail"]

    _inspect(client, task["id"], "pass", day="2026-02-01")  # re-inspected after re-clearance
    assert client.patch(f"/api/hazards/{hid}", json={"status": "released"}).status_code == 200


def test_every_completed_clearance_task_needs_a_pass(client: TestClient) -> None:
    hid = make_hazard(client, SQUARE)["id"]
    prepare_for_release(client, hid)
    second = _clearance_task(client, hid, "completed")
    res = client.patch(f"/api/hazards/{hid}", json={"status": "released"})
    assert res.status_code == 409 and second["code"] in res.json()["detail"]
