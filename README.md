# mine-action-core

[![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)

An **IMSMA-inspired** mine action information management system: track hazardous
areas, the tasks assigned to them, the clearance work done and its QA, on a map with 3D terrain.

> Independent portfolio project. Not affiliated with or endorsed by GICHD, and
> not a copy of IMSMA. All data is **synthetic**: the country of Karvonia and every record
> are fictional.
> (Replace `OWNER/REPO` in the badge above after pushing to GitHub.)

## What it does

| Area | Highlights |
|------|-----------|
| **Map** | Hazards by status, **3D terrain with relief shading** (free elevation tiles, adjustable exaggeration), spatial-issue markers, per-hazard detail |
| **Lifecycle** | `suspected → confirmed → in_clearance → released` (or `cancelled`), enforced identically by the API and the importer |
| **QA/QC** | Inspections on clearance tasks; a hazard can only be released after a **passing** latest inspection, with no open tasks and no spatial errors |
| **Field reports** | Surveyors register findings on a phone with GPS; reports queue **offline** and send themselves later without duplicates; IM staff triage them against nearby hazards into a new suspected area, a link, or a rejection ([docs/field-reports.md](docs/field-reports.md)) |
| **Roles** | viewer / surveyor / editor / QA officer / admin. Hazard data is public to read; field reports are not; data entry is separated from QA and release |
| **Import** | CSV (WKT) or GeoJSON, dry run by default, per-row rejection report, CRS reprojection, duplicate and overlap detection, role-aware |
| **Spatial checks** | Overlaps, release conflicts, near-miss gaps, slivers, spikes, tiny areas; adjacency and contiguous clusters ([docs/topology.md](docs/topology.md)) |
| **Audit trail** | Every create/update/delete with old and new values, source (`api`, `import:<id>`, `seed`) and **who** did it |
| **Dashboard & reports** | Release progress by region, status and month; downloadable progress and clearance reports, re-importable hazard export (CSV/GeoJSON) |
| **Ops** | One-container production image, Fly.io example, CI with lint, tests against PostGIS and a 90% coverage floor |

## Stack

PostgreSQL 16 + PostGIS · FastAPI · SQLAlchemy 2 + GeoAlchemy2 · Alembic · Shapely + pyproj ·
PyJWT · React + TypeScript · MapLibre GL · Docker Compose · pytest · GitHub Actions

## Quick start

Requires Docker (with Compose).

```bash
make up      # builds and starts db, API, and frontend
make seed    # loads synthetic data, topology test cases and demo accounts
```

- App: http://localhost:5173 (click **Log in**; demo accounts are listed on the form)
- API docs (Swagger, with an Authorize button): http://localhost:8000/docs
- Tests: `make test` · coverage: `make coverage` · lint: `make lint`

Demo accounts (local dev only, password `demo-password`): `viewer`, `surveyor`, `editor`, `qa`, `admin`.

- Log in as `surveyor` on a phone-sized window: you land on the report form. Send a finding,
  then try it with the network off (it queues and sends when you are back online).
- Log in as `editor`, open **Field reports**, and review the inbox: one report lies inside released land.
- Try releasing a hazard as `editor` (refused), then as `qa` after recording a passing inspection.

### Try the 3D terrain

Tick **3D terrain and relief shading** in the sidebar. Drag with the right mouse button (or
Ctrl + drag) to tilt and rotate; use the slider for vertical exaggeration. The seed sits on
mountainous terrain in central Norway so there is relief to see; Karvonia itself is fictional.

### Try the import

Log in as `editor`, open **Import**, and upload a file from [samples/](samples/). Dry run first, then commit.

## Architecture

```
React + MapLibre (3D terrain from raster-dem tiles)
        │  /api  (JWT bearer, role-based permissions)
        ▼
     FastAPI ──routers──▶ rules.py (lifecycle, QA, release gate)
        │                 topology.py (PostGIS spatial checks)
        │                 importer.py (parse → validate → apply)
        ▼
PostgreSQL + PostGIS:  hazards ─< tasks ─< clearance_records
                          │        └─< qa_inspections       users · audit_log
                          └─< field_reports (point, from the field; reviewed into hazards)
```

| Entity | Purpose |
|--------|---------|
| `hazards` | Suspected/confirmed hazardous areas (`MULTIPOLYGON`, EPSG:4326), with geodesic `area_m2` |
| `tasks` | Survey, clearance or verification work against one hazard |
| `clearance_records` | Dated reports of area cleared and items found/destroyed under a task |
| `qa_inspections` | QA/QC sampling of a clearance task: sample area, residual items, pass/fail |
| `field_reports` | Findings from surveyors (GPS point, item, source), with review outcome and linked hazard |
| `users` | Accounts with a role (scrypt-hashed passwords) |
| `audit_log` | Append-only change history with source and actor |

Terminology is in [docs/glossary.md](docs/glossary.md).

## Design decisions

- **Geometry validation at the boundary.** All client geometry passes through `app/geo.py`
  (self-intersections, non-polygon types, out-of-range coordinates such as projected metres sent as lon/lat).
- **Geodesic measurements.** Areas, perimeters and distances use PostGIS `geography`, so they are real
  metres, not degrees.
- **Real PostGIS in tests.** Spatial behaviour is the point, so tests run against a real database.
- **One rule set, two entry points.** Lifecycle, QA and release rules live in `app/rules.py` and are called by
  both the REST API and the importer, so there is no back door around them.
- **Separation of duties.** Whoever enters or clears data cannot sign it off: release needs the `release`
  permission (QA officer/admin), and QA inspections need `qa`. Editors have neither.
- **Errors block, warnings inform.** Spatial errors (overlaps, release conflicts) stop a release; warnings
  (slivers, near misses) only appear in reports and imports.
- **Duplicates vs overlaps.** IoU >= 0.9 means the same hazard (rejected); a smaller overlap is a warning
  because adjacent hazards legitimately touch.
- **Validation never writes.** `importer.validate` is side-effect free, which makes dry runs trustworthy.
- **Reads public, writes authenticated.** Visitors can browse the demo; every change is attributable.
- **Offline-first field capture.** Field reports get a device-generated id and the server treats
  repeats as the same report, so the outbox can retry blindly without duplicates.
- **Small first load.** Each tab is lazy-loaded; the map engine (~800 kB) only downloads with the
  Map tab, so the field form opens fast on a weak connection (about 50 kB gzipped to start).
- **Spreadsheet-safe exports.** Text cells starting with `= + - @` are neutralised against CSV formula injection.
- **String enums + CHECK constraints** and **hand-written, reversible migrations.**

## Deploying

The repo builds into a single container. See [docs/DEPLOY.md](docs/DEPLOY.md) (Fly.io + Neon example, environment
variables, what to check before going public). I have built and run the image locally but have **not**
deployed it to a public host.

## Limitations

- Login throttling (5 failures per username and address per 5 minutes) is in-memory, so it is
  per process; demo credentials are public in demo mode (see DEPLOY.md).
- The field outbox works offline, but the app itself must be opened online once (no service worker
  yet), and field reports have no photo attachments yet.
- Only hazard status has transition rules; task status is unrestricted.
- Spatial checks run on demand over all hazards (fine for thousands of polygons, not millions) and never
  auto-repair geometry.
- Imports are limited to 5 MB / 5000 rows and run in one request.
- Seed hazards are placed on real terrain in central Norway, so the basemap shows real place names near
  fictional hazards. The 3D view uses free public tile servers (OpenStreetMap, AWS terrain tiles) which are
  fine for development but not for heavy traffic.
- Not included: a demo GIF and a live URL (both need the owner's accounts).
