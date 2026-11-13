"""field reports and the surveyor role

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-12
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ROLES_OLD = "role IN ('viewer','editor','qa_officer','admin')"
ROLES_NEW = "role IN ('viewer','surveyor','editor','qa_officer','admin')"


def upgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", ROLES_NEW)

    op.create_table(
        "field_reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(32), nullable=True, unique=True),
        sa.Column("client_id", sa.String(64), nullable=False, unique=True),
        sa.Column("reported_by", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finding_type", sa.String(20), nullable=False),
        sa.Column("item_category", sa.String(20), nullable=True),
        sa.Column("quantity", sa.Integer, nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "location",
            geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("gps_accuracy_m", sa.Float, nullable=True),
        sa.Column("region", sa.String(80), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="submitted"),
        sa.Column("reviewed_by", sa.String(64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text, nullable=True),
        sa.Column(
            "hazard_id",
            sa.Integer,
            sa.ForeignKey("hazards.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "finding_type IN ('item_found','suspected_area','accident','other')",
            name="ck_fr_finding_type",
        ),
        sa.CheckConstraint(
            "item_category IS NULL OR item_category IN "
            "('ap_mine','av_mine','uxo','submunition','ied','unknown')",
            name="ck_fr_item_category",
        ),
        sa.CheckConstraint(
            "source IN ('direct_observation','local_informant','authority')",
            name="ck_fr_source",
        ),
        sa.CheckConstraint("status IN ('submitted','accepted','rejected')", name="ck_fr_status"),
        sa.CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_fr_quantity"),
        sa.CheckConstraint("gps_accuracy_m IS NULL OR gps_accuracy_m >= 0", name="ck_fr_accuracy"),
    )
    op.create_index(
        "ix_field_reports_location", "field_reports", ["location"], postgresql_using="gist"
    )
    op.create_index("ix_field_reports_status", "field_reports", ["status"])
    op.create_index("ix_field_reports_reported_by", "field_reports", ["reported_by"])


def downgrade() -> None:
    op.drop_table("field_reports")
    # Surveyor accounts cannot exist under the old constraint.
    op.execute("DELETE FROM users WHERE role = 'surveyor'")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", ROLES_OLD)
