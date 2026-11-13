"""The whole story, through the API, the way a programme would live it.

A surveyor reports a finding -> the IM officer turns it into a suspected hazard ->
non-technical survey confirms it -> technical survey reduces part of it -> clearance clears
the rest -> QA passes -> the QA officer releases it. Every step is checked, including who
may do what, and the figures that come out at the end.
"""

from fastapi.testclient import TestClient


def test_from_field_report_to_released_land(as_role, anon: TestClient) -> None:
    surveyor, editor, qa = as_role("surveyor"), as_role("editor"), as_role("qa_officer")

    # 1. A finding in the field.
    report = surveyor.post(
        "/api/field-reports",
        json={"client_id": "story-0001", "observed_at": "2026-01-02T09:00:00Z", "finding_type": "item_found",
              "item_category": "ap_mine", "quantity": 2, "lon": 18.0, "lat": 15.0},
    ).json()  # fmt: skip

    # 2. Triage: a new suspected hazard area, 60 m around the point.
    decision = editor.post(
        f"/api/field-reports/{report['id']}/accept", json={"mode": "new_hazard", "radius_m": 60}
    ).json()
    hid = decision["hazard_id"]
    hazard = anon.get(f"/api/hazards/{hid}").json()
    assert (hazard["hazard_type"], hazard["status"], hazard["hazard_class"]) == (
        "SHA",
        "suspected",
        "anti_personnel",
    )
    area = hazard["area_m2"]

    def task(task_type: str) -> int:
        return editor.post(
            "/api/tasks", json={"hazard_id": hid, "task_type": task_type, "organisation": "Northgate", "status": "active"}
        ).json()["id"]  # fmt: skip

    def progress(task_id: int, m2: float, items: int = 0) -> None:
        res = editor.post(
            "/api/clearance-records",
            json={"task_id": task_id, "record_date": "2026-02-01", "area_cleared_m2": m2,
                  "items_found": items, "items_destroyed": items, "team": "Alpha"},
        )  # fmt: skip
        assert res.status_code == 201, res.text

    # 3. Non-technical survey confirms contamination: SHA -> CHA.
    nts = task("survey")
    editor.patch(f"/api/tasks/{nts}", json={"status": "completed"})
    assert (
        editor.patch(
            f"/api/hazards/{hid}", json={"status": "confirmed", "hazard_type": "CHA"}
        ).status_code
        == 200
    )

    # 4. Technical survey reduces 40 %, clearance clears the rest and finds the two mines.
    ts = task("technical_survey")
    progress(ts, area * 0.4)
    editor.patch(f"/api/tasks/{ts}", json={"status": "completed"})
    assert editor.patch(f"/api/hazards/{hid}", json={"status": "in_clearance"}).status_code == 200
    clearance = task("clearance")
    progress(clearance, area * 0.6, items=2)
    editor.patch(f"/api/tasks/{clearance}", json={"status": "completed"})

    # 5. Nobody but QA may sign off; QA inspects both land-release tasks.
    assert editor.patch(f"/api/hazards/{hid}", json={"status": "released"}).status_code == 403
    assert qa.patch(f"/api/hazards/{hid}", json={"status": "released"}).status_code == 409
    for t in (ts, clearance):
        assert (
            qa.post(
                "/api/qa-inspections",
                json={"task_id": t, "inspection_date": "2026-02-05", "outcome": "pass"},
            ).status_code
            == 201
        )

    # 6. Release.
    assert qa.patch(f"/api/hazards/{hid}", json={"status": "released"}).status_code == 200

    # 7. What the public sees.
    dash = anon.get("/api/dashboard").json()
    assert dash["release_percent"] == 100 and dash["outstanding_area_m2"] == 0
    release = dash["land_release"]
    assert round(release["reduced_m2"]) == round(area * 0.4) and round(
        release["cleared_m2"]
    ) == round(area * 0.6)
    assert release["items_destroyed"] == 2 and dash["qa"]["pass_rate"] == 100
    summaries = [a["summary"] for a in dash["recent_activity"]]
    assert f"{hazard['code']}: in clearance → released" in summaries
    history = anon.get("/api/audit", params={"entity_type": "hazard", "entity_id": hid}).json()
    assert [h["actor"] for h in history][:1] == ["qa_officer"] and history[-1]["source"].startswith(
        "field_report:"
    )
