from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import topology
from app.db import get_db
from app.models import Hazard
from app.schemas import (
    AdjacencyEdge,
    ClusterMember,
    ClusterOut,
    TopologyClusters,
    TopologyIssue,
    TopologyReport,
)

router = APIRouter(prefix="/topology", tags=["topology"])
DbDep = Annotated[Session, Depends(get_db)]


@router.get("/check", response_model=TopologyReport)
def check_topology(
    db: DbDep,
    hazard_id: int | None = None,
    gap_tolerance_m: Annotated[float, Query(ge=0.1, le=50)] = topology.DEFAULT_GAP_TOLERANCE_M,
    min_severity: Literal["info", "warning", "error"] = "info",
) -> TopologyReport:
    """Run all topology rules. See docs/topology.md for the rules and thresholds.

    With `hazard_id` only issues involving that hazard are returned.
    """
    if hazard_id is not None and db.get(Hazard, hazard_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Hazard {hazard_id} not found")
    checked, issues = topology.check(db, hazard_id, gap_tolerance_m)
    floor = topology.SEVERITY_RANK[min_severity]
    issues = [i for i in issues if topology.SEVERITY_RANK[i.severity] >= floor]
    by_severity: dict[str, int] = {}
    by_rule: dict[str, int] = {}
    for i in issues:
        by_severity[i.severity] = by_severity.get(i.severity, 0) + 1
        by_rule[i.rule] = by_rule.get(i.rule, 0) + 1
    return TopologyReport(
        checked_hazards=checked,
        issue_count=len(issues),
        by_severity=by_severity,
        by_rule=by_rule,
        issues=[
            TopologyIssue(
                rule=i.rule,
                severity=i.severity,
                message=i.message,
                hazard_ids=i.hazard_ids,
                hazard_codes=i.hazard_codes,
                location=i.location,
                value=i.value,
            )
            for i in issues
        ],
    )


@router.get("/adjacency", response_model=list[AdjacencyEdge])
def get_adjacency(db: DbDep) -> list[AdjacencyEdge]:
    """Pairs of hazards that share a boundary without overlapping."""
    return [AdjacencyEdge(**vars(e)) for e in topology.adjacency(db)]


@router.get("/clusters", response_model=TopologyClusters)
def get_clusters(
    db: DbDep, min_size: Annotated[int, Query(ge=2, le=100)] = 2
) -> TopologyClusters:
    """Contiguous groups of hazards connected by shared edges, largest area first."""
    found, isolated = topology.clusters(db, min_size)
    return TopologyClusters(
        cluster_count=len(found),
        clustered_hazards=sum(len(c.members) for c in found),
        isolated_hazards=isolated,
        clusters=[
            ClusterOut(
                hazard_count=len(c.members),
                total_area_m2=c.total_area_m2,
                shared_boundary_m=c.shared_boundary_m,
                regions=c.regions,
                status_counts=c.status_counts,
                members=[ClusterMember(**m) for m in c.members],
            )
            for c in found
        ],
    )
