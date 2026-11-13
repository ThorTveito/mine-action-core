from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import (
    AccidentActivity,
    FindingType,
    HazardClass,
    HazardStatus,
    HazardType,
    InspectionOutcome,
    InspectionType,
    ItemCategory,
    ReleaseMethod,
    ReportSource,
    ReportStatus,
    Role,
    Sex,
    TaskStatus,
    TaskType,
    VictimOutcome,
)


class HazardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    hazard_type: HazardType
    hazard_class: HazardClass
    status: HazardStatus = HazardStatus.SUSPECTED
    region: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="Omit to assign the administrative area that contains the hazard",
    )
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
    """A land-release record. `release_method` follows the task type when omitted."""

    task_id: int
    record_date: date
    area_cleared_m2: float = Field(default=0.0, ge=0, description="Area released, in m2")
    release_method: ReleaseMethod | None = None
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
    release_method: ReleaseMethod
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
    actor: str
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
    items_found: int = 0


class ClassBreakdown(BaseModel):
    hazard_class: str
    hazard_count: int
    area_m2: float


class OrganisationStats(BaseModel):
    organisation: str
    tasks: int
    active_tasks: int
    completed_tasks: int
    cleared_area_m2: float
    items_destroyed: int


class QaSummary(BaseModel):
    inspections: int
    passed: int
    failed: int
    pass_rate: float | None  # percent, None when there are no inspections
    residual_items: int


class FieldReportSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    by_finding_type: dict[str, int]
    median_review_hours: float | None


class DataQuality(BaseModel):
    errors: int
    warnings: int
    by_rule: dict[str, int]


class ActivityItem(BaseModel):
    at: datetime
    entity_type: str
    action: str
    source: str  # api | import | seed | field report
    summary: str


class Dashboard(BaseModel):
    region: str | None = None  # the filter applied, None for all regions
    regions: list[str] = []  # every region, for the filter
    hazard_count: int = 0
    open_hazard_count: int = 0  # suspected + confirmed + in_clearance
    contaminated_area_m2: float  # all hazards except cancelled
    remaining_area_m2: float  # suspected + confirmed + in_clearance
    released_area_m2: float
    cancelled_area_m2: float
    release_percent: float
    items_found: int = 0
    items_destroyed: int = 0
    area_by_status: dict[str, float]
    hazards_by_status: dict[str, int] = {}
    hazards_by_class: list[ClassBreakdown] = []
    tasks_by_status: dict[str, int]
    tasks_by_type: dict[str, int] = {}
    by_region: list[RegionProgress]
    monthly_clearance: list[MonthlyClearance]
    organisations: list[OrganisationStats] = []
    qa: QaSummary | None = None
    outstanding_area_m2: float = 0.0  # open hazards minus land already released inside them
    land_release: "LandRelease | None" = None
    casualties: "Casualties | None" = None
    risk_education: "RiskEducationSummary | None" = None
    top_priorities: list["PriorityOut"] = []
    # The sections below always cover all regions.
    field_reports: FieldReportSummary | None = None
    data_quality: DataQuality | None = None
    recent_activity: list[ActivityItem] = []


# ---- Tier 3: users, QA ---------------------------------------------------------------


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: Role
    is_active: bool


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    role: Role
    password: str = Field(min_length=8, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class DemoUser(BaseModel):
    username: str
    role: Role


class Meta(BaseModel):
    demo_mode: bool
    demo_password: str | None
    demo_users: list[DemoUser]


class QaInspectionCreate(BaseModel):
    task_id: int
    inspection_type: InspectionType = InspectionType.QA
    inspection_date: date
    sample_area_m2: float = Field(default=0.0, ge=0)
    residual_items_found: int = Field(default=0, ge=0)
    outcome: InspectionOutcome
    notes: str | None = None

    @model_validator(mode="after")
    def _pass_means_no_residuals(self) -> Self:
        if self.outcome == InspectionOutcome.PASS and self.residual_items_found > 0:
            raise ValueError("An inspection that found residual items cannot pass")
        return self


class QaInspectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    inspection_type: InspectionType
    inspection_date: date
    inspector: str
    sample_area_m2: float
    residual_items_found: int
    outcome: InspectionOutcome
    notes: str | None
    created_at: datetime


# ---- Tier 3: topology ----------------------------------------------------------------


class TopologyIssue(BaseModel):
    rule: str
    severity: Literal["info", "warning", "error"]
    message: str
    hazard_ids: list[int]
    hazard_codes: list[str]
    location: dict[str, Any] | None
    value: float | None


class TopologyReport(BaseModel):
    checked_hazards: int
    issue_count: int
    by_severity: dict[str, int]
    by_rule: dict[str, int]
    issues: list[TopologyIssue]


class AdjacencyEdge(BaseModel):
    a_id: int
    a_code: str
    b_id: int
    b_code: str
    shared_boundary_m: float


class ClusterMember(BaseModel):
    id: int
    code: str
    status: str
    region: str


class ClusterOut(BaseModel):
    hazard_count: int
    total_area_m2: float
    shared_boundary_m: float
    regions: list[str]
    status_counts: dict[str, int]
    members: list[ClusterMember]


class TopologyClusters(BaseModel):
    cluster_count: int
    clustered_hazards: int
    isolated_hazards: int
    clusters: list[ClusterOut]


# ---- Field reports ---------------------------------------------------------------------

# Allow a little clock skew between field devices and the server.
_FUTURE_TOLERANCE_MIN = 10


class FieldReportCreate(BaseModel):
    client_id: str = Field(
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9-]+$",
        description="Generated on the device; resending the same id never creates a duplicate",
    )
    observed_at: datetime
    finding_type: FindingType
    item_category: ItemCategory | None = None
    quantity: int | None = Field(default=None, ge=0, le=10_000)
    source: ReportSource = ReportSource.DIRECT_OBSERVATION
    description: str = Field(default="", max_length=2000)
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    gps_accuracy_m: float | None = Field(default=None, ge=0, le=10_000)
    region: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        from datetime import UTC, timedelta

        observed = self.observed_at
        if observed.tzinfo is None:  # treat naive device time as UTC
            observed = observed.replace(tzinfo=UTC)
            self.observed_at = observed
        if observed > datetime.now(UTC) + timedelta(minutes=_FUTURE_TOLERANCE_MIN):
            raise ValueError("observed_at is in the future; check the device clock")
        if self.finding_type == FindingType.ITEM_FOUND:
            if self.item_category is None:
                raise ValueError("item_category is required when an item was found")
            if not self.quantity:
                raise ValueError("quantity must be at least 1 when an item was found")
        return self


class FieldReportRead(BaseModel):
    id: int
    code: str
    client_id: str
    reported_by: str
    observed_at: datetime
    received_at: datetime
    finding_type: FindingType
    item_category: ItemCategory | None
    quantity: int | None
    source: ReportSource
    description: str
    lon: float
    lat: float
    gps_accuracy_m: float | None
    region: str | None
    status: ReportStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None
    hazard_id: int | None
    hazard_code: str | None


class NearbyHazard(BaseModel):
    id: int
    code: str
    name: str
    status: HazardStatus
    region: str
    distance_m: float
    contains_point: bool


class VictimIn(BaseModel):
    sex: Sex = Sex.UNKNOWN
    age: int | None = Field(default=None, ge=0, le=120)
    outcome: VictimOutcome
    is_deminer: bool = False


class AcceptReport(BaseModel):
    mode: Literal["new_hazard", "link", "accident"]
    hazard_id: int | None = Field(default=None, description="Required when mode is 'link'")
    radius_m: float = Field(
        default=50, ge=5, le=2000, description="Size of the new suspected area around the point"
    )
    name: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=2000)
    # mode "accident": the victims and what they were doing (no names are ever stored)
    victims: list[VictimIn] = Field(default_factory=list, max_length=100)
    activity: AccidentActivity = AccidentActivity.UNKNOWN

    @model_validator(mode="after")
    def _link_needs_hazard(self) -> Self:
        if self.mode == "link" and self.hazard_id is None:
            raise ValueError("hazard_id is required when mode is 'link'")
        return self


class RejectReport(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class ReportDecision(BaseModel):
    report: FieldReportRead
    hazard_id: int | None
    warnings: list[str]
    accident_id: int | None = None


# ---- Accidents, victims, risk education, admin areas -------------------------------------


class VictimOut(VictimIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class AccidentCreate(BaseModel):
    occurred_on: date
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    item_category: ItemCategory | None = None
    activity: AccidentActivity = AccidentActivity.UNKNOWN
    description: str = Field(default="", max_length=2000)
    victims: list[VictimIn] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _not_in_future(self) -> Self:
        if self.occurred_on > date.today():
            raise ValueError("occurred_on is in the future")
        return self


class AccidentRead(BaseModel):
    id: int
    code: str
    occurred_on: date
    lon: float
    lat: float
    region: str | None
    item_category: ItemCategory | None
    activity: AccidentActivity
    description: str
    hazard_id: int | None
    hazard_code: str | None
    field_report_id: int | None
    recorded_by: str
    killed: int
    injured: int
    victims: list[VictimOut]


class RiskEducationCreate(BaseModel):
    held_on: date
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    organisation: str = Field(min_length=1, max_length=80)
    girls: int = Field(default=0, ge=0, le=100_000)
    boys: int = Field(default=0, ge=0, le=100_000)
    women: int = Field(default=0, ge=0, le=100_000)
    men: int = Field(default=0, ge=0, le=100_000)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _someone_attended(self) -> Self:
        if self.girls + self.boys + self.women + self.men == 0:
            raise ValueError("a session needs at least one participant")
        if self.held_on > date.today():
            raise ValueError("held_on is in the future")
        return self


class RiskEducationRead(BaseModel):
    id: int
    code: str
    held_on: date
    lon: float
    lat: float
    region: str | None
    organisation: str
    girls: int
    boys: int
    women: int
    men: int
    total: int
    notes: str | None


# ---- Analytics: land release, casualties, risk education, priorities, annual report ------


class LandReleaseYear(BaseModel):
    year: int
    cancelled: float
    reduced: float
    cleared: float
    items_destroyed: int


class LandRelease(BaseModel):
    cancelled_m2: float
    reduced_m2: float
    cleared_m2: float
    total_m2: float
    items_found: int
    items_destroyed: int
    by_year: list[LandReleaseYear]


class CasualtyYear(BaseModel):
    year: int
    accidents: int
    killed: int
    injured: int


class Casualties(BaseModel):
    accidents: int
    casualties: int
    killed: int
    injured: int
    deminers: int
    by_sex: dict[str, int]
    by_age_group: dict[str, int]
    sadd: dict[str, int]  # "<sex>_<child|adult|unknown>" -> count
    by_activity: dict[str, int]
    by_year: list[CasualtyYear]


class EoreYear(BaseModel):
    year: int
    sessions: int
    people: int


class RiskEducationSummary(BaseModel):
    sessions: int
    girls: int
    boys: int
    women: int
    men: int
    total: int
    by_year: list[EoreYear]


class PriorityComponent(BaseModel):
    factor: float
    value: Any
    points: float
    why: str


class PriorityOut(BaseModel):
    rank: int
    hazard_id: int
    code: str
    name: str
    region: str
    status: str
    hazard_class: str
    area_m2: float
    score: float
    components: dict[str, PriorityComponent]


class RegionSnapshot(BaseModel):
    region: str
    open_hazards: int
    outstanding_m2: float
    cancelled_m2: float
    reduced_m2: float
    cleared_m2: float


class AnnualReport(BaseModel):
    year: int
    country: str
    generated_at: datetime
    open_hazards: int
    outstanding_m2: float
    regions: list[RegionSnapshot]
    land_release: LandRelease
    casualties: Casualties
    risk_education: RiskEducationSummary
    qa: QaSummary


Dashboard.model_rebuild()
