"""audit trail

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.Integer, nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("changes", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source", sa.String(64), nullable=False, server_default="api"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("action IN ('create','update','delete')", name="ck_audit_action"),
    )
    op.create_index("ix_audit_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("ix_audit_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_log")
