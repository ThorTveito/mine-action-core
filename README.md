# mine-action-core

An **IMSMA-inspired** mine action information management system: track hazardous
areas, the tasks assigned to them, and the clearance work done, on a map.

> Independent portfolio project. Not affiliated with or endorsed by GICHD, and
> not a copy of IMSMA. All data is **synthetic** and set in the fictional
> country of Karvonia.

## Status

**Tier 1 (done):** PostGIS schema + migrations, deterministic synthetic seed, CRUD API for
hazards / tasks / clearance records, map UI, Docker Compose.
**Tier 2 (done):** import pipeline with rejection reports, enforced status transitions,
audit trail, progress dashboard.
**Next (Tier 3):** roles, QA/QC workflow, reports, hosted demo. See [AGENTS.md](AGENTS.md).

## Highlights

- **Import with a rejection report.** Upload CSV (WKT) or GeoJSON; dry-run by default. Every
  row gets accepted/rejected with machine-readable reasons: `invalid_geometry`,
  `coordinates_out_of_range` (usually projected coordinates sent as lon/lat),
  `duplicate_in_file`, `duplicate_existing`, `overlap` (warning, or error with
  `reject_overlaps`), `invalid_value`, `missing_field`, `unknown_code`,
  `invalid_transition`. Data in another CRS is reprojected (`source_crs=EPSG:32634`).
  `on_error=abort` imports nothing if any row fails. See [samples/](samples/).
- **Hazard lifecycle rules.** `suspected → confirmed → in_clearance → released`, or
  `cancelled`. A hazard can only be released after a completed clearance task and with
  no open tasks. The API and the importer share the same rule code.
- **Audit trail.** Every create/update/delete stores old and new values and its source
  (`api`, `import:<id>`, `seed`). Shown per hazard on the map, queryable at `/api/audit`.
- **Progress dashboard.** Released vs remaining area, by region and status, plus cleared
  area per month, computed in PostGIS-backed queries.

## Stack

PostgreSQL 16 + PostGIS · FastAPI · SQLAlchemy 2 + GeoAlchemy2 · Alembic ·
Shapely · React + TypeScript · MapLibre GL · Docker Compose · pytest

## Quick start

Requires Docker (with Compose).

```bash
make up      # builds and starts db, API, and frontend
make seed    # loads 60 synthetic hazards with tasks and clearance records
```

- App: http://localhost:5173
- API docs (Swagger): http://localhost:8000/docs
- Tests: `make test`

The first `make up` takes a minute while the frontend installs dependencies.

## Architecture

```
React + MapLibre  ──/api──▶  FastAPI  ──▶  PostgreSQL + PostGIS
 (Vite dev proxy)            routers          hazards ─┬─< tasks ─< clearance_records
                             geo.py (validation, GeoJSON <-> PostGIS)
```

| Entity | Purpose |
|--------|---------|
| `hazards` | Suspected/confirmed hazardous areas (`MULTIPOLYGON`, EPSG:4326), with geodesic `area_m2` |
| `tasks` | Survey, clearance or verification work against one hazard |
| `clearance_records` | Dated reports of area cleared and items found/destroyed under a task |
| `audit_log` | Append-only change history for the entities above |

Terminology is explained in [docs/glossary.md](docs/glossary.md).

## Design decisions

- **Geometry validation at the boundary.** All client geometry passes through
  `app/geo.py`, which rejects self-intersections, non-polygon types and
  out-of-range coordinates (a typical symptom of projected metres sent as
  lon/lat). Bad data never reaches the database.
- **Geodesic areas.** Areas are computed by PostGIS on the `geography` type, so
  they are in real square metres rather than square degrees.
- **Real PostGIS in tests.** Spatial behaviour is the point of the project, so
  tests run against a real PostGIS database instead of mocks.
- **String enums + CHECK constraints** rather than native Postgres enums, which
  keeps migrations simple and reversible.
- **Hand-written, reversible migrations.**
- **Duplicates vs overlaps.** Two polygons with intersection-over-union >= 0.9 are the
  same hazard (rejected). A smaller overlap (>= 10% of the smaller polygon) is only a
  warning, because adjacent hazards legitimately touch. Cancelled hazards are ignored.
- **Same rules everywhere.** Status rules live in `app/rules.py` and are called by both
  the REST API and the importer, so there is no back door around them.
- **Validation never writes.** `importer.validate` is side-effect free, which is what
  makes dry runs trustworthy.

## What I would do next

Tier 3: role-based access (who may release a hazard), a QA/QC workflow, exportable
donor-style reports, a hosted live demo, and moving the seed off real-world geography.

## Limitations

- No authentication; the API is open (local development only), and audit entries
  have no user identity yet.
- Only hazard status has transition rules; task status is unrestricted.
- Imports are limited to 5 MB / 5000 rows and run in one request.
- Seed hazards are placed on an arbitrary patch of real land, so the basemap
  shows real place names near fictional hazards. Worth relocating before a
  public demo.
- The basemap uses OpenStreetMap's public tile server, which is fine for
  development but not for a high-traffic deployment.
