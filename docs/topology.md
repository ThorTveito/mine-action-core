# Topology (spatial checks)

> In the UI this is the **Spatial checks** tab. It is about rules between polygons. The 3D
> *terrain* map is a different feature (see the README).

Hazard polygons are only useful if they agree with each other. This module checks the
spatial rules that must hold **within** a polygon and **between** polygons, and feeds
three places: the REST API, the release gate, and the import pipeline.

Code: [`backend/app/topology.py`](../backend/app/topology.py). All measurements are
geodesic (metres, square metres), never degrees. Cancelled hazards are ignored everywhere.

## Rules

| Rule | Severity | What it means | Threshold |
|------|----------|---------------|-----------|
| `overlap` | error | Two hazards cover the same ground | intersection >= 10 m² |
| `minor_overlap` | warning | A tiny overlap, usually an unsnapped vertex | 1 to 10 m² (below 1 m² is ignored as noise) |
| `release_conflict` | error | A **released** hazard overlaps a hazard that is still contaminated: the same ground is both safe and dangerous | any overlap >= 1 m² |
| `gap` | warning | Two hazards end close to each other without touching (undershoot) | 0 < distance <= tolerance (default 2 m, configurable 0.1 to 50 m) |
| `sliver` | warning | A very thin shape, often the strip left between two polygons | Polsby-Popper compactness `4πA/P²` below 0.02 |
| `tiny_area` | warning | Too small to be a real hazard area | below 25 m² |
| `tiny_hole` | warning | A small interior hole | below 25 m² |
| `spike` | warning | A needle-like vertex | interior angle below 5° |
| `duplicate_vertices` | info | Consecutive vertices at the same position | any |

Shared edges are **not** a problem: two hazards that touch along a boundary are
*adjacent*, which is normal for contiguous contamination.

## Where it is used

1. **`GET /api/topology/check`**: full report. `hazard_id` limits it to one hazard,
   `min_severity` filters, `gap_tolerance_m` sets the near-miss distance. Each issue carries
   a rule, severity, message, the hazards involved, a point location for the map, and the
   measured value.
2. **Release gate.** Moving a hazard to `released` is refused (HTTP 409) while it has any
   error-level issue. Warnings do not block. See `rules.check_release_preconditions`.
3. **Import.** Per-polygon findings and near-misses against existing hazards are reported
   as warnings (`topology_sliver`, `topology_gap`, `topology_tiny_area`, ...). Overlaps and
   duplicates are handled by the import pipeline's own checks.

## Adjacency and clusters

- `GET /api/topology/adjacency`: pairs of hazards sharing at least 1 m of boundary without
  overlapping, with the shared boundary length.
- `GET /api/topology/clusters`: connected components of that graph (union-find). A cluster is
  a contiguous contaminated block, usually planned as one operation; the response gives total
  area, status mix, regions and shared edge length. `min_size` sets the smallest cluster.

## How it is computed

- **Between polygons** uses PostGIS with the spatial index: `a.geom && b.geom` for the
  bounding-box prefilter, `ST_Intersects`, `ST_Intersection` (polygonal part only, via
  `ST_CollectionExtract`), and `::geography` for metres. Near misses prefilter with
  `ST_DWithin` in degrees (generous) and then measure exact geodesic distance.
- **Within a polygon** uses shapely on the geometry plus PostGIS for geodesic area and
  perimeter. Spike angles use a local cos(latitude) scale so they are not distorted.
- Each unordered pair is reported once (`a.id < b.id`).

## Demo data

`make seed` adds twelve hand-made cases in an empty corner of Southern Plains, so the
Topology tab always has something to show: a three-hazard cluster, a 1 m near miss, an
overlap, a release conflict, a sliver, a spike and a tiny area. The 60 random hazards are kept
clear of each other, so those are the **only** issues (a test enforces it).

## Limits

- Checks run over all non-cancelled hazards on demand; there is no incremental index or
  background job, which is fine for thousands of polygons but not millions.
- No automatic repair. Fixing an overlap or snapping a gap is a human decision, so the tool
  reports and blocks rather than editing geometry.
- Only polygon-to-polygon rules; there is no check against external layers (roads, rivers,
  administrative boundaries).
