"""Hazard import pipeline: parse upload -> validate every row -> (optionally) apply.

Design notes
- Validation never touches the database state; `validate` is safe for dry runs.
- Every problem is a stable `code` plus a human-readable message, collected per
  row, so the user gets one complete rejection report instead of fix-one-rerun.
- Errors reject a row; warnings (e.g. partial overlap) let it through.
"""

import csv
import io
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError
from shapely import wkt as shapely_wkt
from shapely.geometry import MultiPolygon, mapping, shape
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import audit, gazetteer, geo, rules, topology
from app.config import get_settings
from app.models import Hazard, HazardClass, HazardStatus, HazardType

MAX_ROWS = 5000
MAX_BYTES = 5 * 1024 * 1024
DUPLICATE_IOU = 0.90  # intersection-over-union at or above this = same hazard
OVERLAP_WARN = 0.10  # share of the smaller polygon covered by another hazard

FIELDS = ("code", "name", "hazard_type", "hazard_class", "status", "region", "description")
REQUIRED_ON_CREATE = ("name", "hazard_type", "hazard_class")  # region: from the gazetteer


class ImportFileError(ValueError):
    """The upload as a whole is unusable (bad format, too large, bad CRS)."""


@dataclass
class Issue:
    code: str
    message: str


@dataclass
class RawRow:
    index: int  # 1-based data row (CSV) or feature number (GeoJSON)
    fields: dict[str, str]
    geometry: dict[str, Any] | str | None  # GeoJSON dict or WKT text


@dataclass
class RowPlan:
    index: int
    label: str
    code: str | None = None
    action: str | None = None  # "create" | "update"
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    values: dict[str, Any] = field(default_factory=dict)
    geom: MultiPolygon | None = None
    hazard: Hazard | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, code: str, message: str) -> None:
        self.errors.append(Issue(code, message))

    def warn(self, code: str, message: str) -> None:
        self.warnings.append(Issue(code, message))


# --------------------------------------------------------------------------- parsing


def make_transformer(source_crs: str) -> Transformer | None:
    """Transformer to EPSG:4326, or None if the source already is EPSG:4326."""
    try:
        crs = CRS.from_user_input(source_crs)
    except CRSError as exc:
        raise ImportFileError(f"Unknown source CRS '{source_crs}'") from exc
    if crs.to_epsg() == 4326:
        return None
    return Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)


def parse_upload(filename: str, content: bytes) -> list[RawRow]:
    if len(content) > MAX_BYTES:
        raise ImportFileError(f"File too large (limit {MAX_BYTES // (1024 * 1024)} MB)")
    try:
        text_content = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFileError("File must be UTF-8 encoded") from exc

    name = filename.lower()
    looks_json = text_content.lstrip().startswith("{")
    if name.endswith((".geojson", ".json")) or looks_json:
        rows = _parse_geojson(text_content)
    elif name.endswith(".csv"):
        rows = _parse_csv(text_content)
    else:
        raise ImportFileError("Unsupported file type: upload a .csv or .geojson file")
    if not rows:
        raise ImportFileError("File contains no rows")
    if len(rows) > MAX_ROWS:
        raise ImportFileError(f"Too many rows ({len(rows)}); limit is {MAX_ROWS}")
    return rows


def _parse_csv(content: str) -> list[RawRow]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ImportFileError("CSV has no header row")
    headers = {h.strip().lower() for h in reader.fieldnames if h}
    if not headers & {"wkt", "geometry"}:
        raise ImportFileError("CSV needs a 'wkt' or 'geometry' column")
    rows: list[RawRow] = []
    for i, record in enumerate(reader, start=1):
        cleaned = {(k or "").strip().lower(): (v or "").strip() for k, v in record.items()}
        raw_geom = cleaned.pop("wkt", "") or cleaned.pop("geometry", "")
        geometry: dict[str, Any] | str | None = None
        if raw_geom.startswith("{"):
            try:
                geometry = json.loads(raw_geom)
            except json.JSONDecodeError:
                geometry = raw_geom  # reported as malformed during validation
        elif raw_geom:
            geometry = raw_geom
        rows.append(RawRow(i, {k: cleaned.get(k, "") for k in FIELDS}, geometry))
    return rows


def _parse_geojson(content: str) -> list[RawRow]:
    try:
        doc = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ImportFileError(f"Invalid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise ImportFileError("GeoJSON must be an object")
    if doc.get("type") == "FeatureCollection":
        features = doc.get("features")
        if not isinstance(features, list):
            raise ImportFileError("FeatureCollection has no 'features' array")
    elif doc.get("type") == "Feature":
        features = [doc]
    else:
        raise ImportFileError("GeoJSON must be a FeatureCollection or Feature")
    rows: list[RawRow] = []
    for i, feature in enumerate(features, start=1):
        props = feature.get("properties") if isinstance(feature, dict) else None
        props = props if isinstance(props, dict) else {}
        fields = {k: "" if props.get(k) is None else str(props[k]).strip() for k in FIELDS}
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        rows.append(RawRow(i, fields, geometry))
    return rows


# ------------------------------------------------------------------------ validation


def _norm(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _parse_enum(raw: str, cls: type, name: str, plan: RowPlan, upper: bool = False) -> Any:
    candidate = raw.strip().upper() if upper else _norm(raw)
    try:
        return cls(candidate)
    except ValueError:
        allowed = ", ".join(m.value for m in cls)
        plan.error("invalid_value", f"{name} '{raw}' is not valid (allowed: {allowed})")
        return None


def _to_geometry(raw: dict[str, Any] | str, transformer: Transformer | None) -> MultiPolygon:
    try:
        parsed = shape(raw) if isinstance(raw, dict) else shapely_wkt.loads(raw)
    except Exception as exc:
        raise geo.GeometryError(f"Malformed geometry: {exc}") from exc
    if transformer is not None:
        try:
            parsed = shapely.transform(
                parsed, lambda c: np.column_stack(transformer.transform(c[:, 0], c[:, 1]))
            )
        except Exception as exc:
            raise geo.GeometryError(f"Reprojection failed: {exc}", code="crs_error") from exc
    return geo.parse_polygonal_geojson(dict(mapping(parsed)))


_OVERLAP_SQL = text(
    """
    WITH g AS (SELECT ST_GeomFromText(:wkt, 4326) AS geom)
    SELECT h.id, h.code,
           ST_Area(ST_Intersection(h.geom, g.geom)::geography) AS inter,
           ST_Area(h.geom::geography) AS a_existing,
           ST_Area(g.geom::geography) AS a_new
    FROM hazards h, g
    WHERE ST_Intersects(h.geom, g.geom)
      AND h.status <> 'cancelled'
      AND (CAST(:self_id AS integer) IS NULL OR h.id <> CAST(:self_id AS integer))
    """
)


def _check_spatial(
    db: Session,
    plan: RowPlan,
    earlier: list[RowPlan],
    reject_overlaps: bool,
) -> None:
    geom = plan.geom
    assert geom is not None
    self_id = plan.hazard.id if plan.hazard is not None else None

    for row in db.execute(_OVERLAP_SQL, {"wkt": geom.wkt, "self_id": self_id}):
        union = row.a_existing + row.a_new - row.inter
        iou = row.inter / union if union else 0.0
        share = row.inter / min(row.a_existing, row.a_new)
        if plan.action == "create" and iou >= DUPLICATE_IOU:
            plan.error(
                "duplicate_existing",
                f"Duplicate of existing hazard {row.code} (overlap {iou:.0%})",
            )
        elif share >= OVERLAP_WARN:
            msg = f"Overlaps existing hazard {row.code} ({share:.0%} of the smaller area)"
            if reject_overlaps:
                plan.error("overlap", msg)
            else:
                plan.warn("overlap", msg)

    for other in earlier:
        if other.geom is None or not other.ok:
            continue
        inter = geom.intersection(other.geom).area
        if inter == 0:
            continue
        union = geom.area + other.geom.area - inter
        iou = inter / union if union else 0.0
        share = inter / min(geom.area, other.geom.area)
        if plan.action == "create" and other.action == "create" and iou >= DUPLICATE_IOU:
            plan.error("duplicate_in_file", f"Duplicate of row {other.index} in this file")
        elif share >= OVERLAP_WARN:
            msg = f"Overlaps row {other.index} in this file ({share:.0%} of the smaller area)"
            if reject_overlaps:
                plan.error("overlap", msg)
            else:
                plan.warn("overlap", msg)


def _check_topology(db: Session, plan: RowPlan) -> None:
    """Per-polygon and near-miss topology findings, reported as warnings."""
    assert plan.geom is not None
    area, perimeter = geo.measures(db, plan.geom)
    for f in topology.geometry_issues(plan.geom, area, perimeter):
        plan.warn(f"topology_{f.rule}", f.message)
    self_id = plan.hazard.id if plan.hazard is not None else None
    for code, dist in topology.near_misses(
        db, plan.geom, topology.DEFAULT_GAP_TOLERANCE_M, self_id
    ):
        plan.warn(
            "topology_gap", f"Near miss: {dist:.2f} m from {code} without touching (undershoot?)"
        )


def validate(
    db: Session,
    rows: list[RawRow],
    transformer: Transformer | None,
    reject_overlaps: bool = False,
    can_release: bool = True,
) -> list[RowPlan]:
    plans: list[RowPlan] = []
    seen_codes: set[str] = set()
    pending_status: dict[int, HazardStatus] = {}

    for raw in rows:
        f = raw.fields
        plan = RowPlan(index=raw.index, label=f["name"] or f["code"] or f"row {raw.index}")
        plan.code = f["code"] or None
        plans.append(plan)

        # 1. Identity: create vs update
        if plan.code:
            if plan.code in seen_codes:
                plan.error("duplicate_in_file", f"Code {plan.code} appears more than once")
            seen_codes.add(plan.code)
            plan.hazard = db.scalar(select(Hazard).where(Hazard.code == plan.code))
            if plan.hazard is None:
                plan.error("unknown_code", f"No existing hazard with code {plan.code}")
            plan.action = "update"
        else:
            plan.action = "create"

        # 2. Field values
        if plan.action == "create":
            for name in REQUIRED_ON_CREATE:
                if not f[name]:
                    plan.error("missing_field", f"{name} is required")
        values: dict[str, Any] = {}
        if f["name"]:
            values["name"] = f["name"][:120]
        if f["region"]:
            values["region"] = f["region"][:80]
        if f["description"]:
            values["description"] = f["description"]
        if f["hazard_type"]:
            values["hazard_type"] = _parse_enum(
                f["hazard_type"], HazardType, "hazard_type", plan, True
            )
        if f["hazard_class"]:
            values["hazard_class"] = _parse_enum(
                f["hazard_class"], HazardClass, "hazard_class", plan
            )
        if f["status"]:
            values["status"] = _parse_enum(f["status"], HazardStatus, "status", plan)
        elif plan.action == "create":
            values["status"] = HazardStatus.SUSPECTED
        plan.values = {k: v for k, v in values.items() if v is not None}

        # 3. Geometry
        if raw.geometry is None or raw.geometry == "":
            if plan.action == "create":
                plan.error("missing_field", "geometry is required")
        else:
            try:
                plan.geom = _to_geometry(raw.geometry, transformer)
            except geo.GeometryError as exc:
                message = str(exc)
                if exc.code == "coordinates_out_of_range":
                    message += (
                        ". If the data is in a projected CRS, set the source CRS (e.g. EPSG:32634)"
                    )
                plan.error(exc.code, message)

        # 4. Status rules
        new_status = plan.values.get("status")
        if new_status == HazardStatus.RELEASED and not can_release:
            plan.error("forbidden", "Your role may not release hazards (needs qa_officer or admin)")
        if new_status is not None:
            if plan.action == "create":
                if (msg := rules.check_initial_status(new_status)) is not None:
                    plan.error("invalid_transition", msg)
            elif plan.hazard is not None:
                current = pending_status.get(plan.hazard.id, plan.hazard.status)
                if (msg := rules.check_transition(current, new_status)) is not None or (
                    new_status == HazardStatus.RELEASED
                    and current != HazardStatus.RELEASED
                    and (msg := rules.check_release_preconditions(db, plan.hazard.id)) is not None
                ):
                    plan.error("invalid_transition", msg)
                if plan.ok:
                    pending_status[plan.hazard.id] = new_status

        # 5. Duplicates and overlaps (only for geometrically valid rows)
        if plan.geom is not None and plan.ok:
            _check_spatial(db, plan, plans[:-1], reject_overlaps)
            _check_topology(db, plan)

    return plans


# ----------------------------------------------------------------------------- apply


def apply(
    db: Session, plans: list[RowPlan], import_id: uuid.UUID, actor: str = "system"
) -> tuple[int, int]:
    """Write all accepted rows. Caller commits. Returns (created, updated)."""
    source = f"import:{import_id}"
    created = updated = 0
    for plan in plans:
        if not plan.ok:
            continue
        values = dict(plan.values)
        if plan.action == "create":
            assert plan.geom is not None
            values["region"] = gazetteer.region_for(db, plan.geom, values.get("region"))
            hazard = Hazard(
                **values,
                geom=geo.to_db_geometry(plan.geom),
                area_m2=geo.area_m2(db, plan.geom),
            )
            db.add(hazard)
            db.flush()
            hazard.code = f"{get_settings().country_code}-HAZ-{hazard.id:05d}"
            audit.record(
                db,
                "hazard",
                hazard.id,
                "create",
                audit.created_values({**values, "code": hazard.code, "area_m2": hazard.area_m2}),
                source,
                actor,
            )
            created += 1
        else:
            hazard = plan.hazard
            assert hazard is not None
            if plan.geom is not None:
                values["area_m2"] = geo.area_m2(db, plan.geom)
            trail = audit.diff(hazard, values)
            if plan.geom is not None:
                trail["geometry"] = ["(previous)", "(updated)"]
                hazard.geom = geo.to_db_geometry(plan.geom)
            for key, value in values.items():
                setattr(hazard, key, value)
            if trail:
                audit.record(db, "hazard", hazard.id, "update", trail, source, actor)
            updated += 1
    return created, updated
