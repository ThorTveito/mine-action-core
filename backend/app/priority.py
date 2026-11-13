"""Evidence-based prioritisation of open hazards.

Each open hazard gets a 0-100 score from five transparent components. The weights are
illustrative: real programmes agree their criteria nationally (with the national authority
and affected communities). What matters here is that the score is explainable: every
component and its points are returned, so a ranking can be argued with.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

WEIGHTS: dict[str, float] = {
    "casualties": 35,  # people hurt nearby recently: the strongest signal of risk
    "reports": 15,  # recent field reports nearby: land is in use, people see items
    "threat": 20,  # anti-personnel mines and submunitions threaten civilians most
    "evidence": 15,  # confirmed contamination outranks suspicion
    "size": 15,  # small areas are released quickly: a quick win frees land sooner
}
THREAT: dict[str, float] = {
    "anti_personnel": 1.0,
    "cluster_munition": 0.9,
    "mixed": 0.8,
    "uxo": 0.6,
    "anti_vehicle": 0.5,
}
EVIDENCE: dict[str, float] = {"confirmed": 1.0, "in_clearance": 1.0, "suspected": 0.5}

CASUALTY_RADIUS_M = 2000
CASUALTY_YEARS = 5
CASUALTY_SATURATION = 8  # this many victims or more scores the full casualty weight
REPORT_RADIUS_M = 1000
REPORT_MONTHS = 12
REPORT_SATURATION = 3
LARGE_AREA_M2 = 500_000  # areas this size or larger score nothing for size

_SQL = text(
    """
    SELECT h.id, h.code, h.name, h.region, h.status, h.hazard_class, h.area_m2,
      (SELECT COUNT(v.id) FROM accidents a JOIN victims v ON v.accident_id = a.id
        WHERE a.occurred_on >= :acc_since
          AND ST_DWithin(a.location, h.geom, :acc_deg)
          AND ST_DWithin(a.location::geography, h.geom::geography, :acc_m)) AS casualties,
      (SELECT COUNT(*) FROM field_reports f
        WHERE f.status <> 'rejected' AND f.observed_at >= :rep_since
          AND ST_DWithin(f.location, h.geom, :rep_deg)
          AND ST_DWithin(f.location::geography, h.geom::geography, :rep_m)) AS reports
    FROM hazards h
    WHERE h.status IN ('suspected', 'confirmed', 'in_clearance')
      AND (CAST(:region AS text) IS NULL OR h.region = CAST(:region AS text))
      AND (CAST(:hid AS integer) IS NULL OR h.id = CAST(:hid AS integer))
    """
)


@dataclass
class Priority:
    hazard_id: int
    code: str
    name: str
    region: str
    status: str
    hazard_class: str
    area_m2: float
    score: float
    rank: int = 0
    components: dict[str, dict[str, Any]] = field(default_factory=dict)


def rank(
    db: Session, region: str | None = None, hazard_id: int | None = None, today: date | None = None
) -> list[Priority]:
    """Score every open hazard (optionally one region or one hazard), highest first."""
    today = today or date.today()
    params = {
        "acc_since": today - timedelta(days=365 * CASUALTY_YEARS),
        "acc_m": CASUALTY_RADIUS_M,
        "acc_deg": CASUALTY_RADIUS_M / 111_000 * 3,
        "rep_since": today - timedelta(days=30 * REPORT_MONTHS),
        "rep_m": REPORT_RADIUS_M,
        "rep_deg": REPORT_RADIUS_M / 111_000 * 3,
        "region": region,
        "hid": hazard_id,
    }
    out: list[Priority] = []
    for r in db.execute(_SQL, params):
        parts = {
            "casualties": (min(1.0, r.casualties / CASUALTY_SATURATION), r.casualties,
                           f"{r.casualties} casualties within {CASUALTY_RADIUS_M / 1000:g} km, last {CASUALTY_YEARS} years"),
            "reports": (min(1.0, r.reports / REPORT_SATURATION), r.reports,
                        f"{r.reports} field reports within {REPORT_RADIUS_M / 1000:g} km, last {REPORT_MONTHS} months"),
            "threat": (THREAT.get(r.hazard_class, 0.5), r.hazard_class,
                       f"threat type: {r.hazard_class.replace('_', ' ')}"),
            "evidence": (EVIDENCE.get(r.status, 0.5), r.status,
                         f"evidence: {r.status.replace('_', ' ')}"),
            "size": (max(0.0, 1 - r.area_m2 / LARGE_AREA_M2), round(r.area_m2),
                     f"{r.area_m2:,.0f} m2 to release"),
        }  # fmt: skip
        components = {
            name: {"factor": round(f, 3), "value": v, "points": round(f * WEIGHTS[name], 1), "why": why}
            for name, (f, v, why) in parts.items()
        }  # fmt: skip
        out.append(
            Priority(
                hazard_id=r.id,
                code=r.code,
                name=r.name,
                region=r.region,
                status=r.status,
                hazard_class=r.hazard_class,
                area_m2=float(r.area_m2),
                score=round(sum(c["points"] for c in components.values()), 1),
                components=components,
            )
        )
    out.sort(key=lambda p: (-p.score, p.code))
    for i, p in enumerate(out, start=1):
        p.rank = i
    return out
