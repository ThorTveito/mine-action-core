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

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    admin = create_engine(base_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()
    command.upgrade(Config("alembic.ini"), "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE audit_log, clearance_records, tasks, hazards RESTART IDENTITY CASCADE"))


@pytest.fixture
def client() -> TestClient:
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
