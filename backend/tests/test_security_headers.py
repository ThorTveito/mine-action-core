from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security_headers import CSP, SecurityHeaders


def test_every_response_carries_security_headers(anon: TestClient) -> None:
    res = anon.get("/api/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert "geolocation=(self)" in res.headers["permissions-policy"]
    assert res.headers["cache-control"] == "no-store"
    assert "content-security-policy" not in res.headers  # dev: no built frontend served


def test_csp_applies_to_the_frontend_but_not_the_api_docs() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeaders, csp=True)

    @app.get("/")
    def index() -> dict[str, str]:
        return {"ok": "yes"}

    client = TestClient(app)
    assert client.get("/").headers["content-security-policy"] == CSP
    assert "content-security-policy" not in client.get("/docs").headers
    assert "frame-ancestors 'none'" in CSP and "https://tile.openstreetmap.org" in CSP
