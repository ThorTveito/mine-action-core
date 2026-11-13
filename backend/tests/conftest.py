"""Tests run against a real PostGIS database (`mac_test`), created on demand."""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

base_url = make_url(
    os.environ.get("DATABASE_URL", "postgresql+psycopg://mac:mac@localhost:5440/mac")
)
TEST_DB = "mac_test"
test_url = base_url.set(database=TEST_DB)
# Must be set before `app` modules are imported.
os.environ["DATABASE_URL"] = test_url.render_as_string(hide_password=False)

from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from app import security
from app.db import SessionLocal, engine
from app.main import app
from app.models import Role, User

PASSWORD = "test-password-123"
ROLES = ("viewer", "surveyor", "editor", "qa_officer", "admin")


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    admin = create_engine(base_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()
    command.upgrade(Config("alembic.ini"), "head")
    with SessionLocal() as db:  # one account per role, kept across tests
        for role in ROLES:
            db.add(
                User(
                    username=role,
                    display_name=role.replace("_", " ").title(),
                    role=Role(role),
                    password_hash=security.hash_password(PASSWORD),
                )
            )
        db.commit()
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    security.login_throttle.clear()
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE audit_log, victims, accidents, risk_education_sessions, field_reports, qa_inspections, clearance_records, tasks, hazards, admin_areas RESTART IDENTITY CASCADE"
            )
        )


def client_as(role: str) -> TestClient:
    token = security.create_token(role, role)
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


@pytest.fixture
def client() -> TestClient:
    """Authenticated as admin, so most tests exercise behaviour rather than permissions."""
    return client_as("admin")


@pytest.fixture
def as_role():
    """Factory: `as_role("editor")` returns a client logged in with that role."""
    return client_as


@pytest.fixture
def anon() -> TestClient:
    return TestClient(app)


SQUARE = {
    "type": "Polygon",
    "coordinates": [[[18.0, 15.0], [18.01, 15.0], [18.01, 15.01], [18.0, 15.01], [18.0, 15.0]]],
}


@pytest.fixture
def hazard_payload() -> dict:
    return {
        "name": "Test Field",
        "hazard_type": "SHA",
        "hazard_class": "anti_personnel",
        "region": "Central Basin",
        "geometry": SQUARE,
    }


@pytest.fixture
def hazard(client: TestClient, hazard_payload: dict) -> dict:
    res = client.post("/api/hazards", json=hazard_payload)
    assert res.status_code == 201, res.text
    return res.json()
