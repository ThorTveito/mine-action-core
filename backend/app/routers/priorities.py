from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import priority
from app.db import get_db
from app.models import Hazard
from app.schemas import PriorityOut

router = APIRouter(tags=["priorities"])
DbDep = Annotated[Session, Depends(get_db)]


@router.get("/priorities", response_model=list[PriorityOut])
def list_priorities(
    db: DbDep,
    region: str | None = None,
    hazard_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 1000,
) -> list[PriorityOut]:
    """Open hazards ranked by an explainable 0-100 score (see docs/prioritisation.md).

    Every component and its points are included. With `hazard_id`, the one hazard
    (its rank is then within itself; use the full list for the overall rank).
    """
    if hazard_id is not None and db.get(Hazard, hazard_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Hazard {hazard_id} not found")
    return [PriorityOut(**vars(p)) for p in priority.rank(db, region, hazard_id)[:limit]]


@router.get("/priorities/weights")
def weights() -> dict[str, object]:
    """The scoring weights and thresholds, published so the ranking can be scrutinised."""
    return {
        "weights": priority.WEIGHTS,
        "threat": priority.THREAT,
        "evidence": priority.EVIDENCE,
        "casualty_radius_m": priority.CASUALTY_RADIUS_M,
        "casualty_years": priority.CASUALTY_YEARS,
        "report_radius_m": priority.REPORT_RADIUS_M,
        "report_months": priority.REPORT_MONTHS,
        "large_area_m2": priority.LARGE_AREA_M2,
    }
