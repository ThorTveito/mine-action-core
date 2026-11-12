"""Topology: rules that must hold between and within hazard polygons.

Two families of checks:

* **Within one polygon** (shapely, in memory): slivers, tiny areas, spikes, tiny holes,
  duplicate vertices. These are digitising or conversion artefacts.
* **Between polygons** (PostGIS, uses the spatial index): overlaps, release conflicts and
  near-miss gaps. Cancelled hazards are ignored throughout.

The same checks power the REST API, the QA release gate (errors block release) and the
import pipeline (surfaced there as warnings).

Measurements are geodesic (metres), never degrees.
"""

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Literal

import shapely
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy import text
from sqlalchemy.orm import Session

Severity = Literal["info", "warning", "error"]
SEVERITY_RANK: dict[str, int] = {"info": 0, "warning": 1, "error": 2}

# Thresholds (metres / square metres / degrees / ratio). Documented in docs/topology.md.
OVERLAP_NOISE_M2 = 1.0  # intersections smaller than this are numerical noise
OVERLAP_ERROR_M2 = 10.0  # at or above this an overlap is an error, below a warning
MIN_AREA_M2 = 25.0  # smaller polygons are probably digitising mistakes
SLIVER_COMPACTNESS = 0.02  # Polsby-Popper 4*pi*A/P^2; a circle is 1, a thin strip near 0
SPIKE_DEGREES = 5.0  # interior angle below this is a spike
DEFAULT_GAP_TOLERANCE_M = 2.0  # nearer than this but not touching = suspicious gap
MIN_SHARED_BOUNDARY_M = 1.0  # polygons are "adjacent" if they share at least this much edge


@dataclass
class Issue:
    rule: str
    severity: Severity
    message: str
    hazard_ids: list[int]
    hazard_codes: list[str]
    location: dict[str, Any] | None = None  # GeoJSON Point
    value: float | None = None  # the measured quantity (m2, m, degrees, ratio)


@dataclass
class GeometryFinding:
    rule: str
    severity: Severity
    message: str
    point: tuple[float, float] | None
    value: float | None = None


def _point(lon: float, lat: float) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [lon, lat]}


# ----------------------------------------------------------------- within one polygon


def compactness(area_m2: float, perimeter_m: float) -> float:
    """Polsby-Popper score: 1 for a circle, approaching 0 for a long thin strip."""
    return 4 * math.pi * area_m2 / (perimeter_m**2) if perimeter_m > 0 else 0.0


def _ring_angles(ring_coords: list[tuple[float, float]], lat_scale: float) -> list[tuple[float, float, float]]:
    """(lon, lat, interior-angle-in-degrees) for each vertex of a closed ring."""
    pts = ring_coords[:-1] if ring_coords and ring_coords[0] == ring_coords[-1] else ring_coords
    n = len(pts)
    out: list[tuple[float, float, float]] = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        v1 = ((p0[0] - p1[0]) * lat_scale, p0[1] - p1[1])
        v2 = ((p2[0] - p1[0]) * lat_scale, p2[1] - p1[1])
        n1, n2 = math.hypot(*v1), math.hypot(*v2)
        if n1 == 0 or n2 == 0:
            continue
        cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
        out.append((p1[0], p1[1], math.degrees(math.acos(cos))))
    return out


def geometry_issues(geom: MultiPolygon | Polygon, area_m2: float, perimeter_m: float) -> list[GeometryFinding]:
    """Checks that look at one polygon on its own."""
    findings: list[GeometryFinding] = []
    centroid = geom.representative_point()
    here = (centroid.x, centroid.y)

    if area_m2 < MIN_AREA_M2:
        findings.append(
            GeometryFinding(
                "tiny_area",
                "warning",
                f"Area is only {area_m2:.1f} m2 (minimum mappable is {MIN_AREA_M2:.0f} m2); "
                "probably a digitising mistake",
                here,
                area_m2,
            )
        )
    else:
        score = compactness(area_m2, perimeter_m)
        if score < SLIVER_COMPACTNESS:
            findings.append(
                GeometryFinding(
                    "sliver",
                    "warning",
                    f"Very thin shape (compactness {score:.3f}, below {SLIVER_COMPACTNESS}); "
                    "often a leftover strip between two polygons",
                    here,
                    score,
                )
            )

    polygons = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    lat_scale = math.cos(math.radians(centroid.y))
    spikes: list[tuple[float, float, float]] = []
    duplicates = 0
    for poly in polygons:
        for ring in [poly.exterior, *poly.interiors]:
            coords = list(ring.coords)
            duplicates += sum(1 for a, b in itertools.pairwise(coords) if a == b)
            spikes += [v for v in _ring_angles(coords, lat_scale) if v[2] < SPIKE_DEGREES]
        for hole in poly.interiors:
            hole_m2 = Polygon(hole).area / geom.area * area_m2 if geom.area else 0.0
            if hole_m2 < MIN_AREA_M2:
                c = Polygon(hole).representative_point()
                findings.append(
                    GeometryFinding(
                        "tiny_hole",
                        "warning",
                        f"Interior hole of about {hole_m2:.1f} m2 (below {MIN_AREA_M2:.0f} m2)",
                        (c.x, c.y),
                        hole_m2,
                    )
                )
    for lon, lat, angle in sorted(spikes, key=lambda v: v[2])[:3]:
        findings.append(
            GeometryFinding(
                "spike",
                "warning",
                f"Spike: a vertex with an interior angle of {angle:.1f} degrees "
                f"(below {SPIKE_DEGREES:.0f})",
                (lon, lat),
                angle,
            )
        )
    if duplicates:
        findings.append(
            GeometryFinding(
                "duplicate_vertices",
                "info",
                f"{duplicates} consecutive duplicate vertices",
                here,
                float(duplicates),
            )
        )
    return findings


# ------------------------------------------------------------- between polygons (PostGIS)

_HAZARDS_SQL = text(
    """
    SELECT id, code, status, area_m2,
           ST_Perimeter(geom::geography) AS perimeter,
           ST_AsBinary(geom) AS wkb
    FROM hazards
    WHERE status <> 'cancelled' AND (CAST(:hid AS integer) IS NULL OR id = CAST(:hid AS integer))
    ORDER BY id
    """
)

_OVERLAP_SQL = text(
    """
    SELECT a.id AS a_id, a.code AS a_code, a.status AS a_status,
           b.id AS b_id, b.code AS b_code, b.status AS b_status,
           ST_Area(ST_CollectionExtract(ST_Intersection(a.geom, b.geom), 3)::geography) AS inter,
           ST_X(ST_PointOnSurface(ST_CollectionExtract(ST_Intersection(a.geom, b.geom), 3))) AS lon,
           ST_Y(ST_PointOnSurface(ST_CollectionExtract(ST_Intersection(a.geom, b.geom), 3))) AS lat
    FROM hazards a
    JOIN hazards b ON a.id < b.id AND a.geom && b.geom AND ST_Intersects(a.geom, b.geom)
    WHERE a.status <> 'cancelled' AND b.status <> 'cancelled'
      AND (CAST(:hid AS integer) IS NULL OR a.id = CAST(:hid AS integer) OR b.id = CAST(:hid AS integer))
    """
)

_GAP_SQL = text(
    """
    SELECT a.id AS a_id, a.code AS a_code, b.id AS b_id, b.code AS b_code,
           ST_Distance(a.geom::geography, b.geom::geography) AS dist,
           ST_X(ST_ClosestPoint(a.geom, b.geom)) AS lon,
           ST_Y(ST_ClosestPoint(a.geom, b.geom)) AS lat
    FROM hazards a
    JOIN hazards b ON a.id < b.id AND ST_DWithin(a.geom, b.geom, :tol_deg)
    WHERE a.status <> 'cancelled' AND b.status <> 'cancelled'
      AND NOT ST_Intersects(a.geom, b.geom)
      AND (CAST(:hid AS integer) IS NULL OR a.id = CAST(:hid AS integer) OR b.id = CAST(:hid AS integer))
    """
)

_ADJACENCY_SQL = text(
    """
    SELECT a.id AS a_id, a.code AS a_code, b.id AS b_id, b.code AS b_code,
           COALESCE(ST_Area(ST_CollectionExtract(ST_Intersection(a.geom, b.geom), 3)::geography), 0) AS inter,
           COALESCE(ST_Length(ST_CollectionExtract(
               ST_Intersection(ST_Boundary(a.geom), ST_Boundary(b.geom)), 2)::geography), 0) AS shared
    FROM hazards a
    JOIN hazards b ON a.id < b.id AND a.geom && b.geom AND ST_Intersects(a.geom, b.geom)
    WHERE a.status <> 'cancelled' AND b.status <> 'cancelled'
    """
)

_NEAR_MISS_SQL = text(
    """
    WITH g AS (SELECT ST_GeomFromText(:wkt, 4326) AS geom)
    SELECT h.code, ST_Distance(h.geom::geography, g.geom::geography) AS dist
    FROM hazards h, g
    WHERE h.status <> 'cancelled'
      AND ST_DWithin(h.geom, g.geom, :tol_deg)
      AND NOT ST_Intersects(h.geom, g.geom)
      AND (CAST(:self_id AS integer) IS NULL OR h.id <> CAST(:self_id AS integer))
    """
)


def _tol_deg(tolerance_m: float) -> float:
    """Generous degree-space prefilter for ST_DWithin; exact filtering uses geography."""
    return tolerance_m / 111_000 * 3


def check(
    db: Session, hazard_id: int | None = None, gap_tolerance_m: float = DEFAULT_GAP_TOLERANCE_M
) -> tuple[int, list[Issue]]:
    """Run all topology checks. With `hazard_id`, only issues involving that hazard.

    Returns (number of hazards examined, issues sorted most severe first).
    """
    issues: list[Issue] = []
    rows = db.execute(_HAZARDS_SQL, {"hid": hazard_id}).all()

    for row in rows:
        geom = shapely.from_wkb(bytes(row.wkb))
        for f in geometry_issues(geom, row.area_m2, row.perimeter):
            issues.append(
                Issue(
                    f.rule,
                    f.severity,
                    f"{row.code}: {f.message}",
                    [row.id],
                    [row.code],
                    _point(*f.point) if f.point else None,
                    f.value,
                )
            )

    for row in db.execute(_OVERLAP_SQL, {"hid": hazard_id}):
        if row.inter is None or row.inter < OVERLAP_NOISE_M2:
            continue  # shared edge or numerical noise, not an overlap
        released = {row.a_status == "released", row.b_status == "released"}
        if released == {True, False}:
            rule, severity = "release_conflict", "error"
            what = "A released hazard overlaps a hazard that is still contaminated"
        elif row.inter >= OVERLAP_ERROR_M2:
            rule, severity, what = "overlap", "error", "Hazards overlap"
        else:
            rule, severity, what = "minor_overlap", "warning", "Hazards overlap slightly"
        issues.append(
            Issue(
                rule,
                severity,
                f"{what}: {row.a_code} and {row.b_code} share {row.inter:,.0f} m2",
                [row.a_id, row.b_id],
                [row.a_code, row.b_code],
                _point(row.lon, row.lat) if row.lon is not None else None,
                float(row.inter),
            )
        )

    params = {"hid": hazard_id, "tol_deg": _tol_deg(gap_tolerance_m)}
    for row in db.execute(_GAP_SQL, params):
        if row.dist is None or not (0 < row.dist <= gap_tolerance_m):
            continue
        issues.append(
            Issue(
                "gap",
                "warning",
                f"Near miss: {row.a_code} and {row.b_code} are {row.dist:.2f} m apart without "
                "touching (undershoot?)",
                [row.a_id, row.b_id],
                [row.a_code, row.b_code],
                _point(row.lon, row.lat),
                float(row.dist),
            )
        )

    issues.sort(key=lambda i: (-SEVERITY_RANK[i.severity], i.rule, i.hazard_ids))
    return len(rows), issues


def blocking_errors(db: Session, hazard_id: int) -> list[str]:
    """Messages of error-level topology issues involving this hazard (they block release)."""
    _, issues = check(db, hazard_id)
    return [i.message for i in issues if i.severity == "error"]


def near_misses(
    db: Session, geom: MultiPolygon, tolerance_m: float, self_id: int | None = None
) -> list[tuple[str, float]]:
    """Existing hazards within `tolerance_m` of `geom` but not touching it."""
    out = []
    params = {"wkt": geom.wkt, "tol_deg": _tol_deg(tolerance_m), "self_id": self_id}
    for row in db.execute(_NEAR_MISS_SQL, params):
        if row.dist is not None and 0 < row.dist <= tolerance_m:
            out.append((row.code, float(row.dist)))
    return out


# --------------------------------------------------------------------- adjacency/clusters


@dataclass
class Edge:
    a_id: int
    a_code: str
    b_id: int
    b_code: str
    shared_boundary_m: float


def adjacency(db: Session, min_shared_m: float = MIN_SHARED_BOUNDARY_M) -> list[Edge]:
    """Pairs of hazards that share an edge (without overlapping)."""
    edges = []
    for row in db.execute(_ADJACENCY_SQL):
        if row.inter < OVERLAP_NOISE_M2 and row.shared >= min_shared_m:
            edges.append(Edge(row.a_id, row.a_code, row.b_id, row.b_code, float(row.shared)))
    return edges


@dataclass
class Cluster:
    members: list[dict[str, Any]] = field(default_factory=list)
    total_area_m2: float = 0.0
    shared_boundary_m: float = 0.0
    regions: list[str] = field(default_factory=list)
    status_counts: dict[str, int] = field(default_factory=dict)


def clusters(db: Session, min_size: int = 2) -> tuple[list[Cluster], int]:
    """Contiguous groups of hazards linked by shared edges, largest area first.

    Returns (clusters with at least `min_size` members, number of isolated hazards).
    A contiguous contaminated block is usually planned and resourced as one operation.
    """
    edges = adjacency(db)
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        parent[find(e.a_id)] = find(e.b_id)

    groups: dict[int, set[int]] = {}
    for node in list(parent):
        groups.setdefault(find(node), set()).add(node)

    info = {
        r.id: r
        for r in db.execute(
            text("SELECT id, code, status, region, area_m2 FROM hazards WHERE status <> 'cancelled'")
        )
    }
    boundary_by_root: dict[int, float] = {}
    for e in edges:
        root = find(e.a_id)
        boundary_by_root[root] = boundary_by_root.get(root, 0.0) + e.shared_boundary_m

    result: list[Cluster] = []
    for root, ids in groups.items():
        if len(ids) < min_size:
            continue
        cluster = Cluster(shared_boundary_m=boundary_by_root.get(root, 0.0))
        for hid in sorted(ids):
            h = info[hid]
            cluster.members.append({"id": h.id, "code": h.code, "status": h.status, "region": h.region})
            cluster.total_area_m2 += float(h.area_m2)
            cluster.status_counts[h.status] = cluster.status_counts.get(h.status, 0) + 1
        cluster.regions = sorted({m["region"] for m in cluster.members})
        result.append(cluster)
    result.sort(key=lambda c: -c.total_area_m2)
    isolated = len(info) - sum(len(g) for g in groups.values())
    return result, isolated
