import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import security
from app.config import DEV_SECRET, Settings
from app.db import SessionLocal
from app.models import User
from app.routers import auth_users
from tests.conftest import PASSWORD, client_as
from tests.helpers import box_geojson, make_hazard, prepare_for_release

HAZARD = {
    "name": "H",
    "hazard_type": "SHA",
    "hazard_class": "mixed",
    "region": "Central Basin",
    "geometry": box_geojson(18.0, 15.0, 18.01, 15.01),
}


def login(client: TestClient, username: str, password: str):
    return client.post("/api/auth/login", data={"username": username, "password": password})


# ---------------------------------------------------------------- login and tokens


def test_login_returns_token_and_user(anon: TestClient) -> None:
    res = login(anon, "editor", PASSWORD)
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["role"] == "editor" and body["token_type"] == "bearer"
    me = anon.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["username"] == "editor"


@pytest.mark.parametrize("username,password", [("editor", "wrong"), ("nobody", PASSWORD)])
def test_bad_credentials_are_rejected_identically(anon: TestClient, username: str, password: str) -> None:
    res = login(anon, username, password)
    assert res.status_code == 401
    assert res.json()["detail"] == "Incorrect username or password"


def test_me_needs_a_valid_token(anon: TestClient) -> None:
    assert anon.get("/api/auth/me").status_code == 401
    assert anon.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_token_of_deactivated_user_stops_working(anon: TestClient, as_role) -> None:
    editor = as_role("editor")
    assert editor.get("/api/auth/me").status_code == 200
    with SessionLocal() as db:
        db.query(User).filter_by(username="editor").update({"is_active": False})
        db.commit()
    try:
        assert editor.get("/api/auth/me").status_code == 401
        assert login(anon, "editor", PASSWORD).status_code == 401
    finally:
        with SessionLocal() as db:
            db.query(User).filter_by(username="editor").update({"is_active": True})
            db.commit()


def test_tampered_and_expired_tokens_are_rejected() -> None:
    token = security.create_token("admin", "admin")
    assert security.decode_token(token)["sub"] == "admin"
    assert security.decode_token(token[:-2] + "xx") is None
    assert security.decode_token("a.b.c") is None


def test_password_hashing() -> None:
    stored = security.hash_password("s3cret-pass")
    assert stored.startswith("scrypt$") and "s3cret" not in stored
    assert security.verify_password("s3cret-pass", stored)
    assert not security.verify_password("other", stored)
    assert not security.verify_password("x", "not-a-hash")
    assert security.hash_password("s3cret-pass") != stored  # salted


def test_production_requires_a_real_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", secret_key=DEV_SECRET)
    assert Settings(app_env="production", secret_key="x" * 32).app_env == "production"


# ------------------------------------------------------------------- permissions


def test_anonymous_can_read_but_not_write(anon: TestClient, client: TestClient) -> None:
    make_hazard(client, HAZARD["geometry"])
    assert anon.get("/api/hazards").status_code == 200
    assert anon.get("/api/dashboard").status_code == 200
    assert anon.get("/api/topology/check").status_code == 200
    res = anon.post("/api/hazards", json=HAZARD)
    assert res.status_code == 401 and res.headers["www-authenticate"] == "Bearer"
    assert anon.post("/api/tasks", json={}).status_code == 401
    assert anon.delete("/api/hazards/1").status_code == 401


def test_viewer_is_read_only(as_role) -> None:
    viewer = as_role("viewer")
    assert viewer.get("/api/hazards").status_code == 200
    res = viewer.post("/api/hazards", json=HAZARD)
    assert res.status_code == 403 and "viewer" in res.json()["detail"]


def test_editor_can_enter_data_but_not_delete_inspect_or_release(
    as_role, client: TestClient
) -> None:
    editor = as_role("editor")
    hazard = editor.post("/api/hazards", json=HAZARD).json()
    task = editor.post(
        "/api/tasks",
        json={"hazard_id": hazard["id"], "task_type": "clearance", "organisation": "O"},
    ).json()
    assert editor.post(
        "/api/clearance-records",
        json={"task_id": task["id"], "record_date": "2026-01-01", "team": "T"},
    ).status_code == 201
    assert editor.delete(f"/api/hazards/{hazard['id']}").status_code == 403
    assert editor.post(
        "/api/qa-inspections",
        json={"task_id": task["id"], "inspection_date": "2026-01-02", "outcome": "pass"},
    ).status_code == 403

    prepare_for_release(client, make_hazard(client, box_geojson(18.5, 15.0, 18.51, 15.01))["id"])
    ready = client.get("/api/hazards", params={"status": "in_clearance"}).json()[0]
    res = editor.patch(f"/api/hazards/{ready['id']}", json={"status": "released"})
    assert res.status_code == 403 and "releasing hazards" in res.json()["detail"]


def test_qa_officer_inspects_and_releases_but_cannot_edit(as_role, client: TestClient) -> None:
    qa = as_role("qa_officer")
    assert qa.post("/api/hazards", json=HAZARD).status_code == 403
    hazard = make_hazard(client, HAZARD["geometry"])
    prepare_for_release(client, hazard["id"])
    assert qa.patch(f"/api/hazards/{hazard['id']}", json={"name": "Renamed"}).status_code == 403
    assert qa.patch(f"/api/hazards/{hazard['id']}", json={"status": "cancelled"}).status_code == 403
    assert qa.patch(f"/api/hazards/{hazard['id']}", json={"status": "released"}).status_code == 200


def test_only_admin_deletes_and_manages_users(as_role, client: TestClient) -> None:
    hazard = make_hazard(client, HAZARD["geometry"])
    assert as_role("qa_officer").delete(f"/api/hazards/{hazard['id']}").status_code == 403
    assert as_role("editor").get("/api/users").status_code == 403
    assert as_role("viewer").get("/api/users").status_code == 403
    assert len(client.get("/api/users").json()) >= 4
    assert client.delete(f"/api/hazards/{hazard['id']}").status_code == 204


def test_admin_creates_user_who_can_log_in(client: TestClient, anon: TestClient) -> None:
    body = {"username": "new.user", "display_name": "New", "role": "editor", "password": "long-enough-pw"}
    created = client.post("/api/users", json=body)
    assert created.status_code == 201 and "password" not in created.json()
    assert login(anon, "new.user", "long-enough-pw").status_code == 200
    assert client.post("/api/users", json=body).status_code == 409
    weak = {**body, "username": "x.y", "password": "short"}
    assert client.post("/api/users", json=weak).status_code == 422
    with SessionLocal() as db:
        db.query(User).filter_by(username="new.user").delete()
        db.commit()


def test_audit_records_who_did_it(as_role, client: TestClient) -> None:
    hazard = as_role("editor").post("/api/hazards", json=HAZARD).json()
    entry = client.get("/api/audit", params={"entity_type": "hazard", "entity_id": hazard["id"]}).json()[0]
    assert entry["actor"] == "editor" and entry["source"] == "api"


# ---------------------------------------------------------------------- meta


def test_meta_hides_demo_accounts_unless_demo_mode(anon: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(auth_users, "get_settings", lambda: Settings(demo_mode=False))
    assert anon.get("/api/meta").json() == {"demo_mode": False, "demo_password": None, "demo_users": []}


def test_meta_lists_demo_accounts_in_demo_mode(anon: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(auth_users, "get_settings", lambda: Settings(demo_mode=True, demo_password="pw-x"))
    body = anon.get("/api/meta").json()
    assert body["demo_mode"] and body["demo_password"] == "pw-x"
    assert {u["role"] for u in body["demo_users"]} == {"viewer", "surveyor", "editor", "qa_officer", "admin"}


def test_swagger_authorize_uses_form_login() -> None:
    assert client_as("admin").get("/openapi.json").status_code == 200


# ---------------------------------------------------------------------- throttling


def test_repeated_failures_are_throttled(anon: TestClient) -> None:
    for _ in range(5):
        assert login(anon, "editor", "wrong").status_code == 401
    blocked = login(anon, "editor", PASSWORD)  # even the right password is refused for now
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert login(anon, "admin", PASSWORD).status_code == 200  # other accounts unaffected


def test_successful_login_resets_the_counter(anon: TestClient) -> None:
    for _ in range(4):
        login(anon, "editor", "wrong")
    assert login(anon, "editor", PASSWORD).status_code == 200
    for _ in range(4):
        assert login(anon, "editor", "wrong").status_code == 401


def test_throttle_window_expires() -> None:
    throttle = security.LoginThrottle(max_failures=2, window_s=0.05)
    throttle.failure("k")
    throttle.failure("k")
    assert throttle.retry_after("k") is not None
    import time

    time.sleep(0.06)
    assert throttle.retry_after("k") is None
