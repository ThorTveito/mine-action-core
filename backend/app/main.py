from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import (
    audit_log,
    auth_users,
    clearance,
    exports,
    field_reports,
    hazards,
    imports,
    qa,
    stats,
    tasks,
    topology,
)

app = FastAPI(
    title="mine-action-core",
    version="0.3.0",
    description=(
        "IMSMA-inspired mine action information management API. "
        "Synthetic data only; not affiliated with GICHD."
    ),
)

app.include_router(hazards.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(clearance.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(imports.router, prefix="/api")
app.include_router(audit_log.router, prefix="/api")
app.include_router(auth_users.router, prefix="/api")
app.include_router(qa.router, prefix="/api")
app.include_router(topology.router, prefix="/api")
app.include_router(exports.router, prefix="/api")
app.include_router(field_reports.router, prefix="/api")


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# Single-container deployment: serve the built frontend from the same origin as the API.
_static = get_settings().static_dir
if _static and Path(_static).is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="frontend")
