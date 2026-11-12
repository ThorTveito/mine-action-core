from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import bootstrap, seed
from app.config import Settings
from app.db import SessionLocal
from app.models import User
from tests.conftest import client_as


@pytest.fixture
def seeded() -> Iterator[TestClient]:
    """Seed the test database. The extra demo account the seed adds is removed afterwards."""
    with SessionLocal() as db:
        seed.seed(db)
    yield client_as("admin")
    with SessionLocal() as db:
        db.query(User).filter(User.username == "qa").delete()
        db.commit()


def test_seed_produces_the_documented_dataset(seeded: TestClient) -> None:
    stats = seeded.get("/api/stats").json()
    assert stats["hazard_count"] == seed.HAZARD_COUNT + 12  # random hazards + topology cases
    assert all(n > 0 for n in stats["hazards_by_status"].values())
    # Codes the demo samples refer to must stay stable.
    by_code = {h["code"]: h for h in seeded.get("/api/hazards", params={"limit": 200}).json()}
    assert by_code["KRV-HAZ-00001"]["status"] == "suspected"
    assert by_code["KRV-HAZ-00002"]["status"] == "released"
    assert by_code["KRV-HAZ-00007"]["status"] == "confirmed"


def test_seed_topology_is_exactly_the_deliberate_cases(seeded: TestClient) -> None:
    """Random hazards are kept clear of each other, so only the 12 hand-made cases show up."""
    report = seeded.get("/api/topology/check").json()
    assert report["by_rule"] == {
        "overlap": 1,
        "release_conflict": 1,
        "gap": 1,
        "sliver": 1,
        "spike": 1,
        "tiny_area": 1,
    }
    clusters = seeded.get("/api/topology/clusters").json()
    assert (clusters["cluster_count"], clusters["clustered_hazards"]) == (1, 3)


def test_seeded_releases_are_consistent_with_the_qa_rule(seeded: TestClient) -> None:
    released = seeded.get("/api/hazards", params={"status": "released", "limit": 200}).json()
    assert released
    for hazard in released:
        tasks = seeded.get("/api/tasks", params={"hazard_id": hazard["id"]}).json()
        clearance = [t for t in tasks if t["task_type"] == "clearance"]
        assert clearance and all(t["status"] == "completed" for t in clearance)
        for task in clearance:
            latest = seeded.get("/api/qa-inspections", params={"task_id": task["id"]}).json()[0]
            assert latest["outcome"] == "pass"


def test_seed_is_deterministic(seeded: TestClient) -> None:
    first = seeded.get("/api/dashboard").json()["contaminated_area_m2"]
    with SessionLocal() as db:
        seed.seed(db)
    assert seeded.get("/api/dashboard").json()["contaminated_area_m2"] == first


def test_seed_creates_demo_users_that_can_log_in(seeded: TestClient) -> None:
    res = seeded.post(
        "/api/auth/login", data={"username": "qa", "password": Settings().demo_password}
    )
    assert res.status_code == 200 and res.json()["user"]["role"] == "qa_officer"
    with SessionLocal() as db:
        assert bootstrap.ensure_demo_users(db) == 0  # idempotent


def test_bootstrap_seeds_only_an_empty_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "get_settings", lambda: Settings(demo_mode=True, seed_on_empty=True))
    admin = client_as("admin")
    try:
        bootstrap.main()
        count = admin.get("/api/stats").json()["hazard_count"]
        assert count == seed.HAZARD_COUNT + 12
        admin.delete("/api/hazards/1")
        bootstrap.main()  # not empty any more: must not reseed
        assert admin.get("/api/stats").json()["hazard_count"] == count - 1
    finally:
        with SessionLocal() as db:
            db.query(User).filter(User.username == "qa").delete()
            db.commit()


def test_seed_field_reports_cover_every_review_path(seeded: TestClient) -> None:
    reports = seeded.get("/api/field-reports").json()
    statuses = sorted(r["status"] for r in reports)
    assert statuses == ["accepted", "rejected", "submitted", "submitted", "submitted", "submitted"]
    flagged = [
        r for r in reports
        if any(h["contains_point"] and h["status"] == "released"
               for h in seeded.get(f"/api/field-reports/{r['id']}/nearby").json())
    ]  # fmt: skip
    assert len(flagged) == 1 and flagged[0]["item_category"] == "uxo"


def test_seed_dashboard_review_time_is_plausible(seeded: TestClient) -> None:
    hours = seeded.get("/api/dashboard").json()["field_reports"]["median_review_hours"]
    assert hours == 22.0  # reviewed a day after observation, received two hours after it
