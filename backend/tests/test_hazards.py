import pytest
from fastapi.testclient import TestClient

from tests.helpers import release_hazard


def test_create_hazard_computes_code_and_geodesic_area(hazard: dict) -> None:
    assert hazard["code"] == "KRV-HAZ-00001"
    assert hazard["status"] == "suspected"
    assert hazard["geometry"]["type"] == "MultiPolygon"
    # 0.01 deg x 0.01 deg at lat 15 is roughly 1.07 km x 1.11 km = ~1.2 km2.
    assert 1.1e6 < hazard["area_m2"] < 1.3e6


def test_create_hazard_rejects_invalid_geometry(client: TestClient, hazard_payload: dict) -> None:
    hazard_payload["geometry"] = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
    }
    res = client.post("/api/hazards", json=hazard_payload)
    assert res.status_code == 422
    assert "Invalid geometry" in res.json()["detail"]


def test_create_hazard_rejects_unknown_enum(client: TestClient, hazard_payload: dict) -> None:
    hazard_payload["status"] = "cleaned"
    assert client.post("/api/hazards", json=hazard_payload).status_code == 422


def test_get_hazard_and_not_found(client: TestClient, hazard: dict) -> None:
    assert client.get(f"/api/hazards/{hazard['id']}").json()["name"] == "Test Field"
    res = client.get("/api/hazards/9999")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]


def test_list_filters_by_status_and_region(
    client: TestClient, hazard: dict, hazard_payload: dict
) -> None:
    hazard_payload.update(status="confirmed", region="River Delta")
    client.post("/api/hazards", json=hazard_payload)

    assert len(client.get("/api/hazards").json()) == 2
    confirmed = client.get("/api/hazards", params={"status": "confirmed"}).json()
    assert [h["region"] for h in confirmed] == ["River Delta"]
    assert client.get("/api/hazards", params={"region": "Nowhere"}).json() == []


def test_geojson_endpoint_returns_feature_collection(client: TestClient, hazard: dict) -> None:
    body = client.get("/api/hazards/geojson").json()
    assert body["type"] == "FeatureCollection"
    assert body["features"][0]["properties"]["code"] == "KRV-HAZ-00001"
    assert body["features"][0]["geometry"]["type"] == "MultiPolygon"


def test_patch_status_and_geometry_recomputes_area(client: TestClient, hazard: dict) -> None:
    res = client.patch(f"/api/hazards/{hazard['id']}", json={"status": "confirmed"})
    assert res.status_code == 200
    assert res.json()["status"] == "confirmed"
    assert res.json()["area_m2"] == hazard["area_m2"]

    bigger = {
        "type": "Polygon",
        "coordinates": [[[18.0, 15.0], [18.02, 15.0], [18.02, 15.02], [18.0, 15.02], [18.0, 15.0]]],
    }
    res = client.patch(f"/api/hazards/{hazard['id']}", json={"geometry": bigger})
    assert res.json()["area_m2"] == pytest.approx(hazard["area_m2"] * 4, rel=0.01)


def test_patch_rejects_null_required_field_and_bad_geometry(
    client: TestClient, hazard: dict
) -> None:
    url = f"/api/hazards/{hazard['id']}"
    assert client.patch(url, json={"name": None}).status_code == 422
    assert (
        client.patch(url, json={"geometry": {"type": "Point", "coordinates": [1, 1]}}).status_code
        == 422
    )
    assert client.patch("/api/hazards/9999", json={"status": "confirmed"}).status_code == 404


def test_delete_hazard_cascades_to_tasks(client: TestClient, hazard: dict) -> None:
    task = client.post(
        "/api/tasks",
        json={"hazard_id": hazard["id"], "task_type": "survey", "organisation": "Org"},
    ).json()
    assert client.delete(f"/api/hazards/{hazard['id']}").status_code == 204
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404
    assert client.delete(f"/api/hazards/{hazard['id']}").status_code == 404


def test_stats_reflect_hazards_and_clearance(client: TestClient, hazard: dict) -> None:
    release_hazard(client, hazard["id"], cleared=500, found=3)
    stats = client.get("/api/stats").json()
    assert stats["hazard_count"] == 1
    assert stats["hazards_by_status"]["released"] == 1
    assert stats["released_area_m2"] == pytest.approx(hazard["area_m2"])
    assert stats["cleared_area_m2"] == 500
    assert stats["items_destroyed"] == 3
    assert stats["open_task_count"] == 0


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
