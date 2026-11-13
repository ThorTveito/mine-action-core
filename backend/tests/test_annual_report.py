from fastapi.testclient import TestClient

from tests.helpers import box_geojson, make_hazard, release_hazard


def test_annual_report_covers_the_year(client: TestClient, anon: TestClient) -> None:
    done = make_hazard(client, box_geojson(18.0, 15.0, 18.004, 15.004))
    make_hazard(client, box_geojson(18.2, 15.0, 18.204, 15.004), region="River Delta")
    release_hazard(client, done["id"], cleared=1000, found=2)  # records dated 2026-01-05
    client.post(
        "/api/accidents",
        json={"occurred_on": "2026-02-01", "lon": 18.002, "lat": 15.002, "victims": [{"sex": "female", "age": 9, "outcome": "injured"}]},
    )  # fmt: skip
    client.post(
        "/api/risk-education",
        json={"held_on": "2025-03-01", "lon": 18.1, "lat": 15.1, "organisation": "O", "women": 10},
    )

    report = anon.get("/api/reports/annual", params={"year": 2026}).json()
    assert report["year"] == 2026 and "fictional" in report["country"]
    assert (
        report["land_release"]["cleared_m2"] == 1000
        and report["land_release"]["items_destroyed"] == 2
    )
    assert report["casualties"]["sadd"]["female_child"] == 1
    assert report["risk_education"]["total"] == 0  # that session was in 2025
    assert report["qa"]["passed"] == 1
    assert report["open_hazards"] == 1
    regions = {r["region"]: r for r in report["regions"]}
    assert (
        regions["Central Basin"]["cleared_m2"] == 1000
        and regions["River Delta"]["open_hazards"] == 1
    )

    earlier = anon.get("/api/reports/annual", params={"year": 2025}).json()
    assert earlier["land_release"]["total_m2"] == 0 and earlier["risk_education"]["women"] == 10
    assert anon.get("/api/reports/annual", params={"year": 1800}).status_code == 422
