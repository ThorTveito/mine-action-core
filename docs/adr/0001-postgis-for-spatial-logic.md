# 0001: Spatial logic lives in PostGIS, measured on geography

**Status:** accepted

## Context
Overlaps, near misses, containment, nearest hazard, buffers and areas are central to mine action
data. Doing them in Python (shapely) means loading every polygon into memory; doing them in
degrees gives wrong areas (a square degree is ~1.2e10 m² at the equator and half that at 60°N).

## Decision
Store EPSG:4326 geometry with GiST indexes, and compute measurements on `geography` (metres).
Use a generous degree-space `ST_DWithin` / `&&` prefilter (index-friendly) before the exact
geography test. Shapely is used only for per-polygon checks (spikes, slivers) and parsing.

## Consequences
Correct metres everywhere, and the database does the heavy lifting with its index. Tests must
run against a real PostGIS (they do; no mocks). Very large datasets would still need vector
tiles and incremental checks.
