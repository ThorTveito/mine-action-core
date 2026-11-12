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
- **Tier 2 (done):** CSV/GeoJSON import with validation (geometry validity, CRS,
  duplicates, overlaps, status transitions, rejection report), audit trail,
  progress dashboard.
- **Tier 3 (done, current baseline):** roles and permissions, QA/QC inspections
  gating release, spatial (topology) checks, CSV/GeoJSON exports and reports,
  3D terrain map, single-container deploy config, CI with a coverage floor.
  *Not done:* a deployed live demo (needs the owner's accounts) and a demo GIF.
- **Since Tier 3:** field reports from surveyors (offline outbox, triage into hazards),
  login throttling, lazy-loaded tabs, mobile layout, error boundary.

Do not build features beyond the current tier early. If a task would materially
change scope, ask first.

**Naming:** "topology" in the code and API (`app/topology.py`, `/api/topology/*`)
means *spatial integrity rules between polygons* (overlaps, gaps, slivers). The
UI calls this "Spatial checks". The 3D *terrain* map (relief from elevation
data) is a separate, frontend-only feature. Don't mix the two up.

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
  app/security.py     scrypt password hashing, JWT tokens
  app/auth.py         roles -> permissions, current-user dependencies
  app/topology.py     spatial checks, adjacency, clusters (PostGIS + shapely)
  app/importer.py     import pipeline: parse -> validate -> apply
  app/bootstrap.py    demo users, first-boot seeding (used by the container)
  app/routers/        hazards, tasks, clearance, qa, stats (+dashboard), imports,
                      audit_log, auth_users, topology, exports, field_reports
  app/seed.py         deterministic synthetic data generator
  alembic/            migrations (hand-written, reviewed)
  tests/              pytest, runs against a real PostGIS database
frontend/           Vite + React + TypeScript + MapLibre GL
  src/MapPage.tsx, DashboardPage.tsx, TopologyPage.tsx, ImportPage.tsx   one per tab
  src/HazardDetail.tsx  status change, QA inspections, spatial issues, history
  src/MapView.tsx       MapLibre map incl. 3D terrain (raster-dem) and issue markers
  src/AuthContext.tsx, auth.ts   login state, token storage, UI permission hints
  src/FieldPage.tsx, outbox.ts   field report form, offline outbox, triage inbox
  src/ErrorBoundary.tsx          per-tab crash containment
  src/ItemList.tsx               map sidebar list: search, sort, in-view filter
samples/            demo import files (assume `make seed` data)
docs/               glossary.md (keep in sync with enums), topology.md, field-reports.md, DEPLOY.md
Dockerfile          single-container production image (API + built frontend)
fly.toml, .github/workflows/ci.yml   deploy example and CI
docker-compose.yml  db (PostGIS), backend, frontend
Makefile            common commands
```

## Commands

Everything runs in Docker; no local Postgres is required.

```bash
make up        # start db, backend, frontend (http://localhost:5173, API :8000/docs)
make seed      # (re)load synthetic data (idempotent: wipes and reseeds)
make test      # backend pytest inside the container
make coverage  # tests with a coverage report (CI floor is 90%)
make lint      # ruff
make image     # build the production Docker image
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
- **Permissions** live in `app/auth.py` (`ROLE_PERMISSIONS`). Reads are public;
  every write endpoint takes `Depends(require(Permission.X))` or, where the
  needed permission depends on the change (hazard PATCH), checks with `ensure`.
  Data entry (editor) is deliberately separate from QA and release
  (qa_officer); keep that separation. The frontend mirrors the matrix in
  `src/auth.ts` as a UI hint only. The API is the authority, so update both.
- Audit rows carry `actor` (username) as well as `source`. Pass the acting
  user into `audit.record` and into `importer.apply`.
- Release preconditions (`rules.check_release_preconditions`): a completed
  clearance task, no open tasks, a **passing** latest QA inspection for every
  completed clearance task, and no error-level spatial issues.
- Spatial checks: thresholds are constants at the top of `app/topology.py` and
  documented in `docs/topology.md`; change them together. Warnings never block;
  errors block release.
- Never commit secrets. `SECRET_KEY` must be set when `APP_ENV=production`
  (the app refuses to start otherwise). Demo credentials exist only in demo mode.
- CSV exports must pass text cells through `safe_cell` (formula injection).
- Public endpoints (dashboard, audit log, hazards) must never expose field report text or
  locations, or user names. The audit log hides `field_report`/`user` history from callers
  without the matching permission (`routers/audit_log.py`); the dashboard returns
  aggregates only. Hazards created from a report carry only the report code.
- Field reports: never make them public. Visibility goes through `_visible()` in
  `routers/field_reports.py` (own reports for surveyors, all for VIEW_REPORTS); return 404
  for reports a user may not see. Submissions must stay idempotent on `client_id`, because
  the frontend outbox relies on blind retries.
- Login throttling lives in `security.login_throttle` (in-memory, per process). Tests clear
  it between runs.
- Error responses use FastAPI `HTTPException` with a clear `detail` message.

**Frontend**
- TypeScript strict mode, no `any`. API types live in `src/types.ts`.
- All API calls go through `src/api.ts` and use the relative `/api` prefix
  (Vite proxies it in dev).
- Status colours are defined once (`src/status.ts`) and reused by map and
  legend. Charts follow the dataviz rules: one y-axis per chart, single-series charts use
  the neutral `SERIES` colour (never a status colour), continuous time axes (zero-fill
  missing months), hover tooltips plus a table view, labels next to every colour.
- Browser storage (`localStorage`) must be wrapped in try/catch (see `auth.ts`)
  and the app must work without it.
- Pages are lazy-loaded (`React.lazy` in `App.tsx`); keep heavy libraries out of the
  initial chunk. Field UI must work on a 375 px wide phone (check it with the mobile preset):
  44 px touch targets, 16 px inputs.
- Network calls that a field user makes must survive being offline (see `outbox.ts`).
- The 3D view uses MapLibre `raster-dem` terrain with free keyless AWS terrain
  tiles (Terrarium encoding); keep the attribution string. No Mapbox/other keys.

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
- Tests truncate all data tables between runs (not `users`, which holds one
  account per role for the whole session); if you add a table, add it to the
  TRUNCATE in `tests/conftest.py` and `seed._wipe`.
- The default `client` fixture is logged in as admin. Use `as_role("editor")`,
  `anon`, etc. when a test is about permissions.
- Spatial tests build geometry from small degree boxes near lat 15; see the
  comments in `tests/test_topology.py` for the metre equivalents.
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
- Seed coordinates are shifted onto real mountainous terrain (central Norway,
  `SHIFT_LON/SHIFT_LAT` in `app/seed.py`) so the 3D view has relief. The country
  and every hazard are fictional, but the OSM basemap shows real place names.
  Sample files and the map's default centre follow the seed; regenerate samples
  if you move it again. The seed must keep random hazards clear of each other so
  the only spatial issues are the 12 deliberate cases (a test enforces this).
