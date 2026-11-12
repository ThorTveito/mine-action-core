"""users, QA inspections, audit actor

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "role IN ('viewer','editor','qa_officer','admin')", name="ck_users_role"
        ),
    )

    op.create_table(
        "qa_inspections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "task_id",
            sa.Integer,
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("inspection_type", sa.String(20), nullable=False),
        sa.Column("inspection_date", sa.Date, nullable=False),
        sa.Column("inspector", sa.String(64), nullable=False),
        sa.Column("sample_area_m2", sa.Float, nullable=False, server_default="0"),
        sa.Column("residual_items_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("inspection_type IN ('qa','qc')", name="ck_qa_type"),
        sa.CheckConstraint("outcome IN ('pass','fail')", name="ck_qa_outcome"),
        sa.CheckConstraint("sample_area_m2 >= 0", name="ck_qa_sample_nonneg"),
        sa.CheckConstraint("residual_items_found >= 0", name="ck_qa_residual_nonneg"),
        sa.CheckConstraint(
            "outcome = 'fail' OR residual_items_found = 0", name="ck_qa_pass_no_residual"
        ),
    )
    op.create_index("ix_qa_task_id", "qa_inspections", ["task_id"])

    op.add_column(
        "audit_log",
        sa.Column("actor", sa.String(64), nullable=False, server_default="system"),
    )


def downgrade() -> None:
    op.drop_column("audit_log", "actor")
    op.drop_table("qa_inspections")
    op.drop_table("users")
