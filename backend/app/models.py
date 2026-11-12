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
    SURVEY = "survey"
    CLEARANCE = "clearance"
    VERIFICATION = "verification"


class TaskStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


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
    source: Mapped[str] = mapped_column(String(64), default="api")  # api | import:<uuid>
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClearanceRecord(Base):
    __tablename__ = "clearance_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    record_date: Mapped[date] = mapped_column(Date)
    area_cleared_m2: Mapped[float] = mapped_column(Float, default=0.0)
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_destroyed: Mapped[int] = mapped_column(Integer, default=0)
    team: Mapped[str] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship(back_populates="records")
