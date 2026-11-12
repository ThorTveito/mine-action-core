# AGENTS.md

Guidance for AI coding agents (and humans) working on **mine-action-core**.
`CLAUDE.md` imports this file, so keep this the single source of truth.

## What this project is

A portfolio project modelling the core concepts of an IMSMA-style mine action
information management system (hazards, tasks, clearance records) on
PostgreSQL/PostGIS, with a FastAPI backend and a React + MapLibre frontend.

- **Audience:** hiring managers for IM officer and GIS/data engineering roles
  at mine action organisations. The project must show domain understanding, not
  just CRUD.
- **Not affiliated with GICHD.** IMSMA is their product. We never claim to be
  IMSMA, never copy its schema, UI or documentation, and never use its
  branding. Describe this project as "inspired by IMSMA concepts".
- **Synthetic data only.** The country ("Karvonia"), regions and every record are
  fictional. Never add real hazard, survey, victim or personnel data, and
  never real place names for contaminated areas.

## Roadmap (build in tiers, each tier ends in a working state)

- **Tier 1 (done):** schema + migrations, synthetic seed, CRUD API for
  hazards/tasks/clearance records, map UI, Docker Compose, README.
- **Tier 2 (done, current baseline):** CSV/GeoJSON import with validation
  (geometry validity, CRS, duplicates, overlaps, status transitions, rejection
  report), audit trail, progress dashboard.
- **Tier 3:** role-based access, QA/QC workflow, exportable reports, free-tier
  live-demo deployment, demo GIF, coverage badge.

Do not build later-tier features early. If a task would materially change
scope, ask first.

## Repository layout

```
backend/            FastAPI app (Python 3.12)
  app/main.py         app factory, router registration
  app/config.py       settings from env (pydantic-settings)
  app/db.py           engine, session, get_db dependency
  app/models.py       SQLAlchemy 2.0 + GeoAlchemy2 models and enums
  app/schemas.py      Pydantic request/response models
  app/geo.py          GeoJSON <-> shapely <-> PostGIS helpers, validation
  app/rules.py        hazard status transitions + release preconditions
  app/audit.py        audit-trail helpers (record, diff)
  app/importer.py     import pipeline: parse -> validate -> apply
  app/routers/        hazards, tasks, clearance, stats (+dashboard), imports, audit_log
  app/seed.py         deterministic synthetic data generator
  alembic/            migrations (hand-written, reviewed)
  tests/              pytest, runs against a real PostGIS database
frontend/           Vite + React + TypeScript + MapLibre GL
  src/MapPage.tsx, DashboardPage.tsx, ImportPage.tsx   one file per tab
samples/            demo import files (assume `make seed` data)
docs/glossary.md    domain terms (keep in sync with code enums)
docker-compose.yml  db (PostGIS), backend, frontend
Makefile            common commands
```

## Commands

Everything runs in Docker; no local Postgres is required.

```bash
make up        # start db, backend, frontend (http://localhost:5173, API :8000/docs)
make seed      # (re)load synthetic data (idempotent: wipes and reseeds)
make test      # backend pytest inside the container
make down      # stop; `make nuke` also deletes the database volume
make logs      # tail logs
cd frontend && npm run build   # typecheck + production build
```

## Conventions

**Backend**
- Python 3.12, fully type-annotated. SQLAlchemy 2.0 style (`Mapped[...]`,
  `select()`), never legacy `Query`.
- All geometry is stored as `MULTIPOLYGON`, SRID **4326**. Areas are computed
  in PostGIS with `ST_Area(geom::geography)` (square metres), never in
  degrees.
- Geometry enters through `app/geo.py` only. It rejects invalid geometry,
  out-of-range coordinates, and non-polygon types, and normalises Polygon to
  MultiPolygon. Don't parse GeoJSON elsewhere.
- Schema changes require an Alembic migration. Write it by hand, make it
  reversible, and never edit a migration that has been committed.
- Enums are `StrEnum`s stored as strings with CHECK constraints (no native PG
  enums, so migrations stay simple). Keep `docs/glossary.md` in sync.
- Business rules belong in `app/rules.py` (or the router/service layer) and are
  covered by tests. Routers stay thin. The API and the importer must enforce
  the **same** rules by calling the same functions; never duplicate a rule.
- **Every mutation of hazards, tasks or clearance records writes an audit row**
  (`app/audit.py`) in the same transaction as the change. No audit row for
  no-ops or rejected changes. Audit rows are append-only and never cascade-deleted.
- Hazard status changes go through `rules.check_status_change`: allowed
  transitions are a fixed map, and `released` needs a completed clearance task
  and no open tasks. Illegal changes return 409; illegal initial status 422.
- Import pipeline: `validate` must never write to the DB (dry runs rely on it).
  Every problem is a stable `code` + readable message collected per row, so
  users get one complete report. Add new checks as codes, with tests.
- Error responses use FastAPI `HTTPException` with a clear `detail` message.

**Frontend**
- TypeScript strict mode, no `any`. API types live in `src/types.ts`.
- All API calls go through `src/api.ts` and use the relative `/api` prefix
  (Vite proxies it in dev).
- Status colours are defined once (`src/status.ts`) and reused by map and
  legend.

**General**
- Use IMAS-style terminology consistently (see `docs/glossary.md`): hazard,
  SHA/CHA, survey, clearance, task, release. Prefer "released" over "cleaned".
- Small, focused commits with imperative messages. Do not commit unless asked.
- No secrets in the repo. Local dev credentials in `docker-compose.yml` are
  throwaway and documented as such.
- Don't add dependencies without a reason; mention new ones in the PR/summary.

## Testing

- Backend tests run against real PostGIS (database `mac_test`, created
  automatically). Do not mock the database; spatial behaviour is the point.
- Every new endpoint needs: happy path, validation failure, not-found.
- New import checks need a test per outcome (rejected with the right code,
  and a nearby valid case that is still accepted).
- Tests truncate all tables between runs; if you add a table, add it to the
  TRUNCATE in `tests/conftest.py` and `seed._wipe`.
- Geometry validation changes need tests with invalid inputs (self-
  intersecting ring, out-of-range coordinates, wrong geometry type).
- Before declaring work done: `make test` passes and
  `cd frontend && npm run build` succeeds.

## Definition of done for a change

1. Tests added or updated and passing.
2. Migration included if the schema changed.
3. README / glossary / this file updated if behaviour or commands changed.
4. App verified running via `make up` (for UI changes, check it in a browser).
5. Summary states what was **not** verified.

## Gotchas

- Longitude comes first in GeoJSON and in `ST_MakePoint`: `[lon, lat]`.
- MapLibre expects EPSG:4326 GeoJSON, so the API returns exactly that.
- `make seed` is destructive to the dev database by design (it wipes the audit
  log too; seeded hazards get a single `seed` audit entry).
- Overlap/duplicate thresholds live in `app/importer.py` (`DUPLICATE_IOU`,
  `OVERLAP_WARN`); cancelled hazards are ignored when checking overlaps.
- The seed bypasses the status rules on purpose (it writes final states directly).
- The dev DB is published on host port **5440** (5433 was taken on the author's
  machine). Inside Compose it is always `db:5432`.
- Seed coordinates are an arbitrary patch of real land, so the OSM basemap shows
  real place names near fictional hazards. Known issue; see README limitations.
