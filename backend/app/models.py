from datetime import date, datetime
from enum import StrEnum
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class HazardType(StrEnum):
    SHA = "SHA"
    CHA = "CHA"


class HazardClass(StrEnum):
    ANTI_PERSONNEL = "anti_personnel"
    ANTI_VEHICLE = "anti_vehicle"
    MIXED = "mixed"
    CLUSTER_MUNITION = "cluster_munition"
    UXO = "uxo"


class HazardStatus(StrEnum):
    SUSPECTED = "suspected"
    CONFIRMED = "confirmed"
    IN_CLEARANCE = "in_clearance"
    RELEASED = "released"
    CANCELLED = "cancelled"


class TaskType(StrEnum):
    SURVEY = "survey"  # non-technical survey (NTS): may cancel land
    TECHNICAL_SURVEY = "technical_survey"  # TS: may reduce land
    CLEARANCE = "clearance"  # clears land
    VERIFICATION = "verification"


class ReleaseMethod(StrEnum):
    """How land was released (IMAS land release): by NTS, by TS, or by clearance."""

    CANCELLED = "cancelled"
    REDUCED = "reduced"
    CLEARED = "cleared"


# Which release method each kind of task produces. Verification releases nothing.
RELEASE_METHOD_FOR_TASK: dict["TaskType", ReleaseMethod] = {
    TaskType.SURVEY: ReleaseMethod.CANCELLED,
    TaskType.TECHNICAL_SURVEY: ReleaseMethod.REDUCED,
    TaskType.CLEARANCE: ReleaseMethod.CLEARED,
}


class TaskStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Role(StrEnum):
    VIEWER = "viewer"
    SURVEYOR = "surveyor"  # field staff: submit field reports only
    EDITOR = "editor"
    QA_OFFICER = "qa_officer"
    ADMIN = "admin"


class InspectionType(StrEnum):
    QA = "qa"  # independent quality assurance
    QC = "qc"  # internal quality control by the operator


class InspectionOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class FindingType(StrEnum):
    ITEM_FOUND = "item_found"  # explosive item seen
    SUSPECTED_AREA = "suspected_area"  # evidence or local knowledge of contamination
    ACCIDENT = "accident"  # an explosive incident
    OTHER = "other"


class ItemCategory(StrEnum):
    AP_MINE = "ap_mine"
    AV_MINE = "av_mine"
    UXO = "uxo"
    SUBMUNITION = "submunition"
    IED = "ied"
    UNKNOWN = "unknown"


class ReportSource(StrEnum):
    DIRECT_OBSERVATION = "direct_observation"
    LOCAL_INFORMANT = "local_informant"
    AUTHORITY = "authority"


class AccidentActivity(StrEnum):
    """What the victims were doing (helps target risk education)."""

    FARMING = "farming"
    HERDING = "herding"
    TRAVELLING = "travelling"
    COLLECTING = "collecting"  # wood, food, scrap metal
    PLAYING = "playing"
    HANDLING = "handling"  # tampering with an item
    DEMINING = "demining"
    OTHER = "other"
    UNKNOWN = "unknown"


class Sex(StrEnum):
    FEMALE = "female"
    MALE = "male"
    UNKNOWN = "unknown"


class VictimOutcome(StrEnum):
    KILLED = "killed"
    INJURED = "injured"


class ReportStatus(StrEnum):
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"  # turned into a new hazard or linked to an existing one
    REJECTED = "rejected"


def _enum(cls: type[StrEnum], name: str) -> Enum:
    """Store enum *values* as plain strings; CHECK constraints live in migrations."""
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=False,
        length=20,
        values_callable=lambda e: [m.value for m in e],
    )


class Base(DeclarativeBase):
    pass


class Hazard(Base):
    __tablename__ = "hazards"
    __table_args__ = (Index("ix_hazards_geom", "geom", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str | None] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    hazard_type: Mapped[HazardType] = mapped_column(_enum(HazardType, "hazard_type"))
    hazard_class: Mapped[HazardClass] = mapped_column(_enum(HazardClass, "hazard_class"))
    status: Mapped[HazardStatus] = mapped_column(
        _enum(HazardStatus, "hazard_status"), default=HazardStatus.SUSPECTED
    )
    region: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[Any] = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False))
    area_m2: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tasks: Mapped[list["Task"]] = relationship(back_populates="hazard", cascade="all, delete")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start",
            name="ck_tasks_dates",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str | None] = mapped_column(String(32), unique=True)
    hazard_id: Mapped[int] = mapped_column(ForeignKey("hazards.id", ondelete="CASCADE"))
    task_type: Mapped[TaskType] = mapped_column(_enum(TaskType, "task_type"))
    status: Mapped[TaskStatus] = mapped_column(
        _enum(TaskStatus, "task_status"), default=TaskStatus.PLANNED
    )
    organisation: Mapped[str] = mapped_column(String(80))
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    hazard: Mapped[Hazard] = relationship(back_populates="tasks")
    records: Mapped[list["ClearanceRecord"]] = relationship(
        back_populates="task", cascade="all, delete"
    )


class AuditLog(Base):
    """Append-only record of every change to hazards, tasks and clearance records."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16))  # create | update | delete
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    source: Mapped[str] = mapped_column(String(64), default="api")  # api | import:<uuid> | seed
    actor: Mapped[str] = mapped_column(String(64), default="system")  # username of who did it
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClearanceRecord(Base):
    """A dated land-release record under a task: area released (by its method) and items."""

    __tablename__ = "clearance_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    record_date: Mapped[date] = mapped_column(Date)
    area_cleared_m2: Mapped[float] = mapped_column(Float, default=0.0)
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_destroyed: Mapped[int] = mapped_column(Integer, default=0)
    release_method: Mapped[ReleaseMethod] = mapped_column(
        _enum(ReleaseMethod, "release_method"), default=ReleaseMethod.CLEARED
    )
    team: Mapped[str] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship(back_populates="records")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"))
    password_hash: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QaInspection(Base):
    """A QA/QC inspection of a clearance task (sampling of cleared ground)."""

    __tablename__ = "qa_inspections"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    inspection_type: Mapped[InspectionType] = mapped_column(
        _enum(InspectionType, "inspection_type")
    )
    inspection_date: Mapped[date] = mapped_column(Date)
    inspector: Mapped[str] = mapped_column(String(64))
    sample_area_m2: Mapped[float] = mapped_column(Float, default=0.0)
    residual_items_found: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[InspectionOutcome] = mapped_column(
        _enum(InspectionOutcome, "inspection_outcome")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship()


class FieldReport(Base):
    """A finding registered in the field by a surveyor, waiting for IM review."""

    __tablename__ = "field_reports"
    __table_args__ = (Index("ix_field_reports_location", "location", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str | None] = mapped_column(String(32), unique=True)
    client_id: Mapped[str] = mapped_column(String(64), unique=True)  # idempotent offline resend
    reported_by: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finding_type: Mapped[FindingType] = mapped_column(_enum(FindingType, "finding_type"))
    item_category: Mapped[ItemCategory | None] = mapped_column(_enum(ItemCategory, "item_category"))
    quantity: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[ReportSource] = mapped_column(_enum(ReportSource, "report_source"))
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326, spatial_index=False))
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float)
    region: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[ReportStatus] = mapped_column(
        _enum(ReportStatus, "report_status"), default=ReportStatus.SUBMITTED
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(64))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    hazard_id: Mapped[int | None] = mapped_column(ForeignKey("hazards.id", ondelete="SET NULL"))

    hazard: Mapped[Hazard | None] = relationship()


class AdminArea(Base):
    """First-level administrative area (the gazetteer). Hazards are assigned spatially."""

    __tablename__ = "admin_areas"
    __table_args__ = (Index("ix_admin_areas_geom", "geom", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    geom: Mapped[Any] = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False))


class Accident(Base):
    """An explosive ordnance accident. Victims are recorded without names (data minimisation)."""

    __tablename__ = "accidents"
    __table_args__ = (Index("ix_accidents_location", "location", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str | None] = mapped_column(String(32), unique=True)
    occurred_on: Mapped[date] = mapped_column(Date)
    location: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326, spatial_index=False))
    region: Mapped[str | None] = mapped_column(String(80))
    item_category: Mapped[ItemCategory | None] = mapped_column(_enum(ItemCategory, "item_category"))
    activity: Mapped[AccidentActivity] = mapped_column(_enum(AccidentActivity, "accident_activity"))
    description: Mapped[str] = mapped_column(Text, default="")
    hazard_id: Mapped[int | None] = mapped_column(ForeignKey("hazards.id", ondelete="SET NULL"))
    field_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("field_reports.id", ondelete="SET NULL")
    )
    recorded_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    victims: Mapped[list["Victim"]] = relationship(
        back_populates="accident", cascade="all, delete-orphan", order_by="Victim.id"
    )
    hazard: Mapped[Hazard | None] = relationship()


class Victim(Base):
    __tablename__ = "victims"

    id: Mapped[int] = mapped_column(primary_key=True)
    accident_id: Mapped[int] = mapped_column(ForeignKey("accidents.id", ondelete="CASCADE"))
    sex: Mapped[Sex] = mapped_column(_enum(Sex, "sex"))
    age: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[VictimOutcome] = mapped_column(_enum(VictimOutcome, "victim_outcome"))
    is_deminer: Mapped[bool] = mapped_column(default=False)

    accident: Mapped[Accident] = relationship(back_populates="victims")


class RiskEducationSession(Base):
    """An explosive ordnance risk education (EORE) session, with sex and age breakdown."""

    __tablename__ = "risk_education_sessions"
    __table_args__ = (Index("ix_eore_location", "location", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str | None] = mapped_column(String(32), unique=True)
    held_on: Mapped[date] = mapped_column(Date)
    location: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326, spatial_index=False))
    region: Mapped[str | None] = mapped_column(String(80))
    organisation: Mapped[str] = mapped_column(String(80))
    girls: Mapped[int] = mapped_column(Integer, default=0)
    boys: Mapped[int] = mapped_column(Integer, default=0)
    women: Mapped[int] = mapped_column(Integer, default=0)
    men: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
