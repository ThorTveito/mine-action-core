"""Explainable prioritisation of open hazards."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import priority
from tests.helpers import box_geojson, make_hazard

SMALL = box_geojson(18.0, 15.0, 18.001, 15.001)  # about 1.2 ha


def test_components_add_up_and_are_explained(client: TestClient) -> None:
    make_hazard(client, SMALL, hazard_class="anti_personnel", status="confirmed", hazard_type="CHA")
    p = client.get("/api/priorities").json()[0]
    assert p["rank"] == 1
    assert p["score"] == pytest.approx(sum(c["points"] for c in p["components"].values()), abs=0.11)
    assert p["components"]["threat"]["points"] == 20 and p["components"]["evidence"]["points"] == 15
    assert p["components"]["casualties"]["points"] == 0
    assert "within 2 km" in p["components"]["casualties"]["why"]


def test_casualties_nearby_raise_the_rank(client: TestClient) -> None:
    quiet = make_hazard(client, SMALL, name="Quiet")
    risky = make_hazard(client, box_geojson(18.2, 15.0, 18.201, 15.001), name="Risky")
    client.post(
        "/api/accidents",
        json={"occurred_on": date.today().isoformat(), "lon": 18.205, "lat": 15.0005,
              "activity": "farming", "victims": [{"outcome": "killed"}, {"outcome": "injured"}]},
    )  # fmt: skip
    ranked = client.get("/api/priorities").json()
    assert [r["hazard_id"] for r in ranked] == [risky["id"], quiet["id"]]
    assert ranked[0]["components"]["casualties"]["value"] == 2
    assert ranked[0]["components"]["casualties"]["points"] == round(
        35 * 2 / priority.CASUALTY_SATURATION, 1
    )


def test_only_open_hazards_are_ranked_and_filters_work(client: TestClient) -> None:
    a = make_hazard(client, SMALL)
    b = make_hazard(client, box_geojson(18.2, 15.0, 18.201, 15.001), region="River Delta")
    client.patch(f"/api/hazards/{b['id']}", json={"status": "cancelled"})
    assert [p["hazard_id"] for p in client.get("/api/priorities").json()] == [a["id"]]
    assert client.get("/api/priorities", params={"region": "River Delta"}).json() == []
    assert (
        client.get("/api/priorities", params={"hazard_id": a["id"]}).json()[0]["code"] == a["code"]
    )
    assert client.get("/api/priorities", params={"hazard_id": 999}).status_code == 404


def test_weights_are_published(anon: TestClient) -> None:
    body = anon.get("/api/priorities/weights").json()
    assert sum(body["weights"].values()) == 100


def test_dashboard_lists_top_priorities(client: TestClient) -> None:
    make_hazard(client, SMALL)
    assert client.get("/api/dashboard").json()["top_priorities"][0]["rank"] == 1
