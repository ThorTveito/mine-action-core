"""initial schema: hazards, tasks, clearance records

Revision ID: 0001
Revises:
Create Date: 2026-11-12
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "hazards",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(32), nullable=True, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("hazard_type", sa.String(3), nullable=False),
        sa.Column("hazard_class", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="suspected"),
        sa.Column("region", sa.String(80), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.Geometry("MULTIPOLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("area_m2", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("hazard_type IN ('SHA','CHA')", name="ck_hazards_hazard_type"),
        sa.CheckConstraint(
            "hazard_class IN ('anti_personnel','anti_vehicle','mixed','cluster_munition','uxo')",
            name="ck_hazards_hazard_class",
        ),
        sa.CheckConstraint(
            "status IN ('suspected','confirmed','in_clearance','released','cancelled')",
            name="ck_hazards_status",
        ),
        sa.CheckConstraint("area_m2 >= 0", name="ck_hazards_area_nonneg"),
    )
    op.create_index("ix_hazards_geom", "hazards", ["geom"], postgresql_using="gist")
    op.create_index("ix_hazards_status", "hazards", ["status"])
    op.create_index("ix_hazards_region", "hazards", ["region"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(32), nullable=True, unique=True),
        sa.Column(
            "hazard_id",
            sa.Integer,
            sa.ForeignKey("hazards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
        sa.Column("organisation", sa.String(80), nullable=False),
        sa.Column("planned_start", sa.Date, nullable=True),
        sa.Column("planned_end", sa.Date, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "task_type IN ('survey','clearance','verification')", name="ck_tasks_task_type"
        ),
        sa.CheckConstraint(
            "status IN ('planned','active','suspended','completed','cancelled')",
            name="ck_tasks_status",
        ),
        sa.CheckConstraint(
            "planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start",
            name="ck_tasks_dates",
        ),
    )
    op.create_index("ix_tasks_hazard_id", "tasks", ["hazard_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])

    op.create_table(
        "clearance_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "task_id",
            sa.Integer,
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("record_date", sa.Date, nullable=False),
        sa.Column("area_cleared_m2", sa.Float, nullable=False, server_default="0"),
        sa.Column("items_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("items_destroyed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("team", sa.String(80), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("area_cleared_m2 >= 0", name="ck_clearance_area_nonneg"),
        sa.CheckConstraint("items_found >= 0", name="ck_clearance_found_nonneg"),
        sa.CheckConstraint("items_destroyed >= 0", name="ck_clearance_destroyed_nonneg"),
        sa.CheckConstraint(
            "items_destroyed <= items_found", name="ck_clearance_destroyed_le_found"
        ),
    )
    op.create_index("ix_clearance_task_id", "clearance_records", ["task_id"])


def downgrade() -> None:
    op.drop_table("clearance_records")
    op.drop_table("tasks")
    op.drop_table("hazards")
