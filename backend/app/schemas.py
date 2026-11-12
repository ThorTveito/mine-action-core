from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import HazardClass, HazardStatus, HazardType, TaskStatus, TaskType


class HazardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    hazard_type: HazardType
    hazard_class: HazardClass
    status: HazardStatus = HazardStatus.SUSPECTED
    region: str = Field(min_length=1, max_length=80)
    description: str | None = None
    geometry: dict[str, Any] = Field(description="GeoJSON Polygon or MultiPolygon, EPSG:4326")


class HazardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    hazard_type: HazardType | None = None
    hazard_class: HazardClass | None = None
    status: HazardStatus | None = None
    region: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None
    geometry: dict[str, Any] | None = None


class HazardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    hazard_type: HazardType
    hazard_class: HazardClass
    status: HazardStatus
    region: str
    description: str | None
    area_m2: float
    geometry: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    hazard_id: int
    task_type: TaskType
    status: TaskStatus = TaskStatus.PLANNED
    organisation: str = Field(min_length=1, max_length=80)
    planned_start: date | None = None
    planned_end: date | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _dates_ordered(self) -> Self:
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("planned_end must not be before planned_start")
        return self


class TaskUpdate(BaseModel):
    task_type: TaskType | None = None
    status: TaskStatus | None = None
    organisation: str | None = Field(default=None, min_length=1, max_length=80)
    planned_start: date | None = None
    planned_end: date | None = None
    description: str | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    hazard_id: int
    task_type: TaskType
    status: TaskStatus
    organisation: str
    planned_start: date | None
    planned_end: date | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class ClearanceRecordCreate(BaseModel):
    task_id: int
    record_date: date
    area_cleared_m2: float = Field(default=0.0, ge=0)
    items_found: int = Field(default=0, ge=0)
    items_destroyed: int = Field(default=0, ge=0)
    team: str = Field(min_length=1, max_length=80)
    notes: str | None = None

    @model_validator(mode="after")
    def _destroyed_not_above_found(self) -> Self:
        if self.items_destroyed > self.items_found:
            raise ValueError("items_destroyed cannot exceed items_found")
        return self


class ClearanceRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    record_date: date
    area_cleared_m2: float
    items_found: int
    items_destroyed: int
    team: str
    notes: str | None
    created_at: datetime


class Stats(BaseModel):
    hazard_count: int
    hazards_by_status: dict[str, int]
    total_area_m2: float
    released_area_m2: float
    cleared_area_m2: float
    open_task_count: int
    items_destroyed: int


# ---- Tier 2: audit, import, dashboard ----------------------------------------------


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    action: str
    changes: dict[str, Any]
    source: str
    created_at: datetime


class IssueOut(BaseModel):
    code: str
    message: str


class RowReport(BaseModel):
    row: int
    label: str
    code: str | None
    outcome: Literal["accepted", "rejected"]
    action: Literal["create", "update"] | None
    errors: list[IssueOut]
    warnings: list[IssueOut]


class ImportReport(BaseModel):
    import_id: str
    filename: str
    source_crs: str
    dry_run: bool
    on_error: Literal["skip", "abort"]
    committed: bool
    total: int
    accepted: int
    rejected: int
    created: int
    updated: int
    warning_count: int
    rows: list[RowReport]


class RegionProgress(BaseModel):
    region: str
    hazard_count: int
    total_area_m2: float
    remaining_area_m2: float
    released_area_m2: float
    cleared_area_m2: float


class MonthlyClearance(BaseModel):
    month: str  # YYYY-MM
    cleared_area_m2: float
    items_destroyed: int


class Dashboard(BaseModel):
    contaminated_area_m2: float  # all hazards except cancelled
    remaining_area_m2: float  # suspected + confirmed + in_clearance
    released_area_m2: float
    cancelled_area_m2: float
    release_percent: float
    area_by_status: dict[str, float]
    tasks_by_status: dict[str, int]
    by_region: list[RegionProgress]
    monthly_clearance: list[MonthlyClearance]
