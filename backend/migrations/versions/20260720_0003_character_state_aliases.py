"""add card-scoped state aliases

Revision ID: 20260720_0003
Revises: 20260720_0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260720_0003"
down_revision = "20260720_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "character_state_aliases" in tables:
        return
    op.create_table(
        "character_state_aliases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("alias", sa.String(), nullable=False),
        sa.Column("alias_key", sa.String(), nullable=False),
        sa.Column("semantic", sa.String(), nullable=False),
        sa.Column("canonical_path", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True, server_default="user_confirmed"),
        sa.Column("confidence", sa.Float(), nullable=True, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_id", "alias_key", name="uq_character_state_alias"),
    )
    op.create_index("ix_character_state_aliases_character_id", "character_state_aliases", ["character_id"], unique=False)


def downgrade() -> None:
    raise RuntimeError("Card-scoped alias migration is not downgraded automatically; restore a database backup instead.")
