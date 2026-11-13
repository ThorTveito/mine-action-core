import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.helpers import box_geojson, make_hazard, release_hazard

URL = "/api/field-reports"
# A 0.004-degree box near lat 15 is about 430 m x 444 m.
BOX = box_geojson(18.000, 15.000, 18.004, 15.004)


def report(**extra: object) -> dict:
    body = {
        "client_id": str(uuid.uuid4()),
        "observed_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "finding_type": "item_found",
        "item_category": "ap_mine",
        "quantity": 2,
        "description": "Two mines on the path",
        "lon": 18.010,
        "lat": 15.002,
        "gps_accuracy_m": 5,
    }
    body.update(extra)
    return body


@pytest.fixture
def surveyor(as_role) -> TestClient:
    return as_role("surveyor")


def submit(client: TestClient, **extra: object) -> dict:
    res = client.post(URL, json=report(**extra))
    assert res.status_code == 201, res.text
    return res.json()


# ------------------------------------------------------------------------- submit


def test_surveyor_submits_a_finding(surveyor: TestClient) -> None:
    body = submit(surveyor)
    assert body["code"] == "KRV-FR-00001" and body["status"] == "submitted"
    assert body["reported_by"] == "surveyor"
    assert (body["lon"], body["lat"]) == (18.010, 15.002)
    assert body["hazard_id"] is None


def test_resubmitting_the_same_client_id_is_idempotent(surveyor: TestClient, as_role) -> None:
    payload = report()
    first = surveyor.post(URL, json=payload)
    again = surveyor.post(URL, json=payload)  # e.g. the offline outbox retrying
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"]
    assert len(surveyor.get(URL).json()) == 1
    assert as_role("editor").post(URL, json=payload).status_code == 409


@pytest.mark.parametrize(
    "extra,message",
    [
        ({"item_category": None}, "item_category is required"),
        ({"quantity": 0}, "quantity must be at least 1"),
        ({"observed_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat()}, "in the future"),
        ({"lat": 95}, "less than or equal to 90"),
        ({"client_id": "bad id!"}, "client_id"),
    ],
)
def test_invalid_reports_are_rejected(surveyor: TestClient, extra: dict, message: str) -> None:
    res = surveyor.post(URL, json=report(**extra))
    assert res.status_code == 422 and message in res.text


def test_suspected_area_needs_no_item(surveyor: TestClient) -> None:
    body = submit(
        surveyor,
        finding_type="suspected_area",
        item_category=None,
        quantity=None,
        source="local_informant",
    )
    assert body["item_category"] is None and body["source"] == "local_informant"


def test_naive_timestamps_are_treated_as_utc(surveyor: TestClient) -> None:
    body = submit(surveyor, observed_at="2026-01-02T10:00:00")
    assert body["observed_at"].startswith("2026-01-02T10:00:00")


def test_who_may_submit(anon: TestClient, as_role) -> None:
    assert anon.post(URL, json=report()).status_code == 401
    assert as_role("viewer").post(URL, json=report()).status_code == 403
    assert as_role("qa_officer").post(URL, json=report()).status_code == 403
    assert as_role("editor").post(URL, json=report()).status_code == 201


def test_submission_is_audited(surveyor: TestClient, client: TestClient) -> None:
    body = submit(surveyor)
    entry = client.get(
        "/api/audit", params={"entity_type": "field_report", "entity_id": body["id"]}
    ).json()[0]
    assert entry["actor"] == "surveyor" and entry["action"] == "create"


# ----------------------------------------------------------------------- visibility


def test_surveyors_only_see_their_own_reports(surveyor: TestClient, as_role) -> None:
    mine = submit(surveyor)
    theirs = submit(as_role("editor"))
    assert [r["id"] for r in surveyor.get(URL).json()] == [mine["id"]]
    assert surveyor.get(f"{URL}/{theirs['id']}").status_code == 404  # not 403: no id leak
    assert len(surveyor.get(f"{URL}/geojson").json()["features"]) == 1
    staff = as_role("qa_officer").get(URL).json()
    assert {r["id"] for r in staff} == {mine["id"], theirs["id"]}


def test_reports_are_not_public(anon: TestClient, as_role, surveyor: TestClient) -> None:
    submit(surveyor)
    assert anon.get(URL).status_code == 401
    assert as_role("viewer").get(URL).status_code == 403
    assert anon.get(f"{URL}/geojson").status_code == 401


def test_list_filters_by_status(surveyor: TestClient, client: TestClient) -> None:
    a = submit(surveyor)
    submit(surveyor)
    client.post(f"{URL}/{a['id']}/reject", json={"reason": "duplicate"})
    assert len(client.get(URL, params={"status": "submitted"}).json()) == 1
    assert [r["id"] for r in client.get(URL, params={"status": "rejected"}).json()] == [a["id"]]


# --------------------------------------------------------------------------- triage


def test_nearby_lists_hazards_by_distance(surveyor: TestClient, client: TestClient) -> None:
    hazard = make_hazard(client, BOX)
    far = make_hazard(client, box_geojson(18.05, 15.0, 18.054, 15.004))  # about 4.8 km east
    body = submit(surveyor, lon=18.005, lat=15.002)  # about 107 m east of the box
    nearby = client.get(f"{URL}/{body['id']}/nearby").json()
    assert [h["id"] for h in nearby] == [hazard["id"]]
    assert 90 < nearby[0]["distance_m"] < 125 and not nearby[0]["contains_point"]
    assert far["id"] in [
        h["id"]
        for h in client.get(f"{URL}/{body['id']}/nearby", params={"radius_m": 10_000}).json()
    ]
    assert surveyor.get(f"{URL}/{body['id']}/nearby").status_code == 403


def test_accept_as_new_hazard_creates_a_suspected_area(
    surveyor: TestClient, client: TestClient
) -> None:
    make_hazard(client, box_geojson(18.5, 15.0, 18.504, 15.004), region="River Delta")
    body = submit(surveyor, lon=18.51, lat=15.002, item_category="av_mine")
    res = client.post(f"{URL}/{body['id']}/accept", json={"mode": "new_hazard", "radius_m": 100})
    assert res.status_code == 200, res.text
    decision = res.json()
    hazard = client.get(f"/api/hazards/{decision['hazard_id']}").json()
    assert (hazard["hazard_type"], hazard["status"], hazard["hazard_class"]) == (
        "SHA",
        "suspected",
        "anti_vehicle",
    )
    assert hazard["region"] == "River Delta"  # taken from the nearest hazard
    assert 30_000 < hazard["area_m2"] < 31_500  # pi * 100^2, as a 32-sided polygon
    assert decision["report"]["status"] == "accepted"
    assert decision["report"]["hazard_code"] == hazard["code"]
    assert decision["report"]["reviewed_by"] == "admin"
    # The public hazard must not carry the report's free text or the reporter's name.
    assert "Two mines" not in hazard["description"] and "surveyor" not in hazard["name"]
    assert body["code"] in hazard["description"]
    audit = client.get(
        "/api/audit", params={"entity_type": "hazard", "entity_id": hazard["id"]}
    ).json()[0]
    assert audit["source"] == f"field_report:{body['code']}"


def test_accept_warns_when_the_new_area_overlaps(surveyor: TestClient, client: TestClient) -> None:
    make_hazard(client, BOX)
    body = submit(surveyor, lon=18.0041, lat=15.002)  # just outside: a 100 m buffer overlaps
    decision = client.post(
        f"{URL}/{body['id']}/accept", json={"mode": "new_hazard", "radius_m": 100}
    ).json()
    assert any("overlap" in w for w in decision["warnings"])


def test_accept_by_linking(surveyor: TestClient, client: TestClient) -> None:
    hazard = make_hazard(client, BOX)
    body = submit(surveyor, lon=18.002, lat=15.002)
    decision = client.post(
        f"{URL}/{body['id']}/accept",
        json={"mode": "link", "hazard_id": hazard["id"], "note": "inside"},
    ).json()
    assert decision["hazard_id"] == hazard["id"] and decision["warnings"] == []
    assert decision["report"]["review_note"] == "inside"
    assert len(client.get("/api/hazards").json()) == 1  # nothing new created


def test_finding_inside_released_land_is_flagged(surveyor: TestClient, client: TestClient) -> None:
    hazard = make_hazard(client, BOX)
    release_hazard(client, hazard["id"])
    body = submit(surveyor, lon=18.002, lat=15.002)
    nearby = client.get(f"{URL}/{body['id']}/nearby").json()[0]
    assert nearby["contains_point"] and nearby["status"] == "released"
    decision = client.post(
        f"{URL}/{body['id']}/accept", json={"mode": "link", "hazard_id": hazard["id"]}
    ).json()
    assert "inside RELEASED hazard" in decision["warnings"][0]


def test_triage_rules(surveyor: TestClient, client: TestClient, as_role) -> None:
    body = submit(surveyor)
    url = f"{URL}/{body['id']}"
    assert surveyor.post(f"{url}/reject", json={"reason": "mine"}).status_code == 403
    assert (
        as_role("qa_officer").post(f"{url}/reject", json={"reason": "not credible"}).status_code
        == 403
    )
    assert client.post(f"{url}/accept", json={"mode": "link"}).status_code == 422
    assert client.post(f"{url}/accept", json={"mode": "link", "hazard_id": 999}).status_code == 404
    assert client.post(f"{url}/reject", json={"reason": "x"}).status_code == 422  # too short
    rejected = client.post(f"{url}/reject", json={"reason": "Duplicate of FR-1"}).json()
    assert (
        rejected["report"]["status"] == "rejected"
        and rejected["report"]["review_note"] == "Duplicate of FR-1"
    )
    again = client.post(f"{url}/accept", json={"mode": "new_hazard"})
    assert again.status_code == 409 and "already rejected" in again.json()["detail"]
    assert surveyor.get(url).json()["status"] == "rejected"  # the reporter sees the outcome
    assert client.get(f"{URL}/9999").status_code == 404
