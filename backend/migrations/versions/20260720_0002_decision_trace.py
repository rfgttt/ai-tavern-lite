"""add runtime decision trace

Revision ID: 20260720_0002
Revises: 20260717_0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260720_0002"
down_revision = "20260717_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in inspect(bind).get_columns("turn_snapshots")}
    if "decision_trace_json" not in columns:
        op.add_column("turn_snapshots", sa.Column("decision_trace_json", sa.Text(), nullable=True, server_default="[]"))


def downgrade() -> None:
    raise RuntimeError("Decision trace migration is not downgraded automatically; restore a database backup instead.")
