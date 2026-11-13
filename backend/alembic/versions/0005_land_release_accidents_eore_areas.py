"""land release methods, technical survey, admin areas, accidents/victims, EORE

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _point() -> geoalchemy2.Geometry:
    return geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False)


def upgrade() -> None:
    # Technical survey becomes its own task type.
    op.drop_constraint("ck_tasks_task_type", "tasks", type_="check")
    op.create_check_constraint(
        "ck_tasks_task_type",
        "tasks",
        "task_type IN ('survey','technical_survey','clearance','verification')",
    )

    # Every land-release record says how the land was released; backfill from the task type.
    op.add_column(
        "clearance_records",
        sa.Column("release_method", sa.String(20), nullable=False, server_default="cleared"),
    )
    op.execute(
        """
        UPDATE clearance_records r
        SET release_method = CASE t.task_type
            WHEN 'survey' THEN 'cancelled'
            WHEN 'technical_survey' THEN 'reduced'
            ELSE 'cleared' END
        FROM tasks t WHERE t.id = r.task_id
        """
    )
    op.create_check_constraint(
        "ck_clearance_release_method",
        "clearance_records",
        "release_method IN ('cancelled','reduced','cleared')",
    )

    op.create_table(
        "admin_areas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column(
            "geom",
            geoalchemy2.Geometry("MULTIPOLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
    )
    op.create_index("ix_admin_areas_geom", "admin_areas", ["geom"], postgresql_using="gist")

    op.create_table(
        "accidents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(32), nullable=True, unique=True),
        sa.Column("occurred_on", sa.Date, nullable=False),
        sa.Column("location", _point(), nullable=False),
        sa.Column("region", sa.String(80), nullable=True),
        sa.Column("item_category", sa.String(20), nullable=True),
        sa.Column("activity", sa.String(20), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "hazard_id", sa.Integer, sa.ForeignKey("hazards.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "field_report_id",
            sa.Integer,
            sa.ForeignKey("field_reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("recorded_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "activity IN ('farming','herding','travelling','collecting','playing','handling',"
            "'demining','other','unknown')",
            name="ck_accidents_activity",
        ),
        sa.CheckConstraint(
            "item_category IS NULL OR item_category IN "
            "('ap_mine','av_mine','uxo','submunition','ied','unknown')",
            name="ck_accidents_item_category",
        ),
    )
    op.create_index("ix_accidents_location", "accidents", ["location"], postgresql_using="gist")
    op.create_index("ix_accidents_occurred_on", "accidents", ["occurred_on"])

    op.create_table(
        "victims",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "accident_id",
            sa.Integer,
            sa.ForeignKey("accidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sex", sa.String(20), nullable=False),
        sa.Column("age", sa.Integer, nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("is_deminer", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.CheckConstraint("sex IN ('female','male','unknown')", name="ck_victims_sex"),
        sa.CheckConstraint("outcome IN ('killed','injured')", name="ck_victims_outcome"),
        sa.CheckConstraint("age IS NULL OR (age >= 0 AND age <= 120)", name="ck_victims_age"),
    )
    op.create_index("ix_victims_accident_id", "victims", ["accident_id"])

    op.create_table(
        "risk_education_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(32), nullable=True, unique=True),
        sa.Column("held_on", sa.Date, nullable=False),
        sa.Column("location", _point(), nullable=False),
        sa.Column("region", sa.String(80), nullable=True),
        sa.Column("organisation", sa.String(80), nullable=False),
        sa.Column("girls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("boys", sa.Integer, nullable=False, server_default="0"),
        sa.Column("women", sa.Integer, nullable=False, server_default="0"),
        sa.Column("men", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("recorded_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "girls >= 0 AND boys >= 0 AND women >= 0 AND men >= 0", name="ck_eore_counts"
        ),
    )
    op.create_index(
        "ix_eore_location", "risk_education_sessions", ["location"], postgresql_using="gist"
    )


def downgrade() -> None:
    op.drop_table("risk_education_sessions")
    op.drop_table("victims")
    op.drop_table("accidents")
    op.drop_table("admin_areas")
    op.drop_constraint("ck_clearance_release_method", "clearance_records", type_="check")
    op.drop_column("clearance_records", "release_method")
    op.execute("DELETE FROM tasks WHERE task_type = 'technical_survey'")
    op.drop_constraint("ck_tasks_task_type", "tasks", type_="check")
    op.create_check_constraint(
        "ck_tasks_task_type", "tasks", "task_type IN ('survey','clearance','verification')"
    )
