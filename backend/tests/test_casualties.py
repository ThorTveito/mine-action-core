"""Accidents with victims (sex- and age-disaggregated), and risk education sessions."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.helpers import box_geojson, make_hazard

ACCIDENT = {
    "occurred_on": "2026-02-10",
    "lon": 18.002,
    "lat": 15.002,
    "item_category": "ap_mine",
    "activity": "farming",
    "victims": [
        {"sex": "female", "age": 12, "outcome": "injured"},
        {"sex": "male", "age": 40, "outcome": "killed"},
        {"sex": "male", "outcome": "injured"},
    ],
}


def test_accident_links_the_containing_hazard(client: TestClient) -> None:
    hazard = make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004))
    res = client.post("/api/accidents", json=ACCIDENT)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["code"] == "KRV-ACC-00001" and body["hazard_code"] == hazard["code"]
    assert (body["killed"], body["injured"]) == (1, 2)
    assert body["victims"][0] == {
        "id": body["victims"][0]["id"],
        "sex": "female",
        "age": 12,
        "outcome": "injured",
        "is_deminer": False,
    }


def test_accident_far_from_hazards_links_nothing(client: TestClient) -> None:
    make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004))
    body = client.post("/api/accidents", json={**ACCIDENT, "lon": 18.3}).json()
    assert body["hazard_id"] is None


def test_accident_validation_and_permissions(client: TestClient, as_role, anon: TestClient) -> None:
    future = (date.today() + timedelta(days=3)).isoformat()
    assert (
        client.post("/api/accidents", json={**ACCIDENT, "occurred_on": future}).status_code == 422
    )
    assert (
        client.post(
            "/api/accidents", json={**ACCIDENT, "victims": [{"outcome": "injured", "age": 130}]}
        ).status_code
        == 422
    )
    assert as_role("surveyor").post("/api/accidents", json=ACCIDENT).status_code == 403
    created = as_role("editor").post("/api/accidents", json=ACCIDENT).json()
    # Individual records are staff-only; the public sees aggregates.
    assert anon.get("/api/accidents").status_code == 401
    assert as_role("viewer").get("/api/accidents").status_code == 403
    assert as_role("qa_officer").get(f"/api/accidents/{created['id']}").status_code == 200
    assert len(as_role("editor").get("/api/accidents/geojson").json()["features"]) == 1
    assert as_role("editor").delete(f"/api/accidents/{created['id']}").status_code == 403
    assert client.delete(f"/api/accidents/{created['id']}").status_code == 204
    assert client.get(f"/api/accidents/{created['id']}").status_code == 404


def test_public_dashboard_disaggregates_casualties(client: TestClient, anon: TestClient) -> None:
    client.post("/api/accidents", json=ACCIDENT)
    client.post(
        "/api/accidents",
        json={**ACCIDENT, "occurred_on": "2025-05-01", "activity": "demining",
              "victims": [{"sex": "male", "age": 30, "outcome": "injured", "is_deminer": True}]},
    )  # fmt: skip
    c = anon.get("/api/dashboard").json()["casualties"]
    assert (c["accidents"], c["casualties"], c["killed"], c["injured"], c["deminers"]) == (
        2,
        4,
        1,
        3,
        1,
    )
    assert c["by_sex"] == {"female": 1, "male": 3, "unknown": 0}
    assert c["by_age_group"] == {"child": 1, "adult": 2, "unknown": 1}
    assert c["sadd"]["female_child"] == 1 and c["sadd"]["male_unknown"] == 1
    assert c["by_activity"] == {"farming": 1, "demining": 1}
    assert c["by_year"] == [
        {"year": 2025, "accidents": 1, "killed": 0, "injured": 1},
        {"year": 2026, "accidents": 1, "killed": 1, "injured": 2},
    ]


def test_accident_history_is_not_public(client: TestClient, anon: TestClient) -> None:
    client.post("/api/accidents", json=ACCIDENT)
    assert "accident" not in {e["entity_type"] for e in anon.get("/api/audit").json()}
    assert "accident" in {e["entity_type"] for e in client.get("/api/audit").json()}


def test_field_report_becomes_an_accident(client: TestClient, as_role) -> None:
    hazard = make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004))
    report = as_role("surveyor").post(
        "/api/field-reports",
        json={"client_id": "acc-report-1", "observed_at": "2026-02-10T10:00:00Z", "finding_type": "accident",
              "item_category": "av_mine", "quantity": 1, "lon": 18.002, "lat": 15.002,
              "description": "Named informant, keep private"},
    ).json()  # fmt: skip
    decision = client.post(
        f"/api/field-reports/{report['id']}/accept",
        json={"mode": "accident", "activity": "travelling", "victims": [{"sex": "male", "age": 50, "outcome": "injured"}]},
    ).json()  # fmt: skip
    assert decision["report"]["status"] == "accepted" and decision["hazard_id"] == hazard["id"]
    accident = client.get(f"/api/accidents/{decision['accident_id']}").json()
    assert accident["field_report_id"] == report["id"] and accident["occurred_on"] == "2026-02-10"
    assert accident["activity"] == "travelling" and accident["item_category"] == "av_mine"
    assert "informant" not in accident["description"]


# ------------------------------------------------------------------------- risk education

SESSION = {
    "held_on": "2026-01-15",
    "lon": 18.1,
    "lat": 15.1,
    "organisation": "Org",
    "girls": 20,
    "boys": 25,
    "women": 5,
    "men": 3,
}


def test_risk_education_session_and_summary(client: TestClient, anon: TestClient, as_role) -> None:
    res = client.post("/api/risk-education", json=SESSION)
    assert (
        res.status_code == 201
        and res.json()["total"] == 53
        and res.json()["code"] == "KRV-EORE-00001"
    )
    client.post(
        "/api/risk-education", json={**SESSION, "held_on": "2025-06-01", "girls": 0, "boys": 0}
    )
    assert len(anon.get("/api/risk-education").json()) == 2  # public: counts only
    summary = anon.get("/api/dashboard").json()["risk_education"]
    assert (
        summary["sessions"],
        summary["girls"],
        summary["boys"],
        summary["women"],
        summary["men"],
    ) == (2, 20, 25, 10, 6)
    assert summary["by_year"] == [
        {"year": 2025, "sessions": 1, "people": 8},
        {"year": 2026, "sessions": 1, "people": 53},
    ]
    assert as_role("viewer").post("/api/risk-education", json=SESSION).status_code == 403


@pytest.mark.parametrize(
    "bad", [{"girls": 0, "boys": 0, "women": 0, "men": 0}, {"boys": -1}, {"held_on": "2999-01-01"}]
)
def test_risk_education_validation(client: TestClient, bad: dict) -> None:
    assert client.post("/api/risk-education", json={**SESSION, **bad}).status_code == 422


def test_session_delete_is_admin_only(client: TestClient, as_role) -> None:
    created = client.post("/api/risk-education", json=SESSION).json()
    assert as_role("editor").delete(f"/api/risk-education/{created['id']}").status_code == 403
    assert client.delete(f"/api/risk-education/{created['id']}").status_code == 204
    assert client.delete(f"/api/risk-education/{created['id']}").status_code == 404
