from fastapi import FastAPI

from app.routers import audit_log, clearance, hazards, imports, stats, tasks

app = FastAPI(
    title="mine-action-core",
    version="0.1.0",
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


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
