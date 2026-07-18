"""Establish the AI Tavern Lite schema baseline.

This first revision is intentionally able to adopt an existing unversioned
AI Tavern Lite SQLite database.  Fresh databases receive the complete schema;
legacy databases receive only the known safe, idempotent repairs before Alembic
records the revision.

Revision ID: 20260717_0001
Revises:
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Callable

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260717_0001"
down_revision = None
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _create_if_missing(name: str, creator: Callable[[], None]) -> None:
    if name not in _table_names():
        creator()


def _create_app_settings() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )


def _create_character_groups() -> None:
    op.create_table(
        "character_groups",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_character_groups_name", "character_groups", ["name"], unique=False)


def _create_characters() -> None:
    op.create_table(
        "characters",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("personality", sa.Text(), nullable=True),
        sa.Column("scenario", sa.Text(), nullable=True),
        sa.Column("first_message", sa.Text(), nullable=True),
        sa.Column("normalized_json", sa.Text(), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.Column("avatar_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_characters_name", "characters", ["name"], unique=False)


def _create_personas() -> None:
    op.create_table(
        "personas",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pronouns", sa.String(), nullable=True),
        sa.Column("avatar_path", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_personas_name", "personas", ["name"], unique=False)


def _create_chat_sessions() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("persona_id", sa.String(), nullable=True),
        sa.Column("group_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["character_groups.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["persona_id"], ["personas.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_group_members() -> None:
    op.create_table(
        "group_members",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("group_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["character_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "character_id", name="uq_group_character"),
    )
    op.create_index("ix_group_members_character_id", "group_members", ["character_id"], unique=False)
    op.create_index("ix_group_members_group_id", "group_members", ["group_id"], unique=False)


def _create_memories() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("importance", sa.Float(), nullable=True),
        sa.Column("keywords", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memories_session_id", "memories", ["session_id"], unique=False)


def _create_messages() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("generation_status", sa.String(), nullable=True),
        sa.Column("segments_json", sa.Text(), nullable=True),
        sa.Column("artifacts_json", sa.Text(), nullable=True),
        sa.Column("speaker_metadata_json", sa.Text(), nullable=True),
        sa.Column("render_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_message_session_sequence"),
    )


def _create_session_branches() -> None:
    op.create_table(
        "session_branches",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("parent_message_id", sa.String(), nullable=True),
        sa.Column("messages_json", sa.Text(), nullable=True),
        sa.Column("runtime_state_json", sa.Text(), nullable=True),
        sa.Column("runtime_revision", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_session_branches_session_id", "session_branches", ["session_id"], unique=False)


def _create_session_states() -> None:
    op.create_table(
        "session_states",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("profile_json", sa.Text(), nullable=True),
        sa.Column("initial_state_json", sa.Text(), nullable=True),
        sa.Column("state_json", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )


def _create_turn_snapshots() -> None:
    op.create_table(
        "turn_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("state_before_json", sa.Text(), nullable=True),
        sa.Column("patch_json", sa.Text(), nullable=True),
        sa.Column("state_after_json", sa.Text(), nullable=True),
        sa.Column("events_json", sa.Text(), nullable=True),
        sa.Column("choices_json", sa.Text(), nullable=True),
        sa.Column("dice_json", sa.Text(), nullable=True),
        sa.Column("battle_checks_json", sa.Text(), nullable=True),
        sa.Column("battle_json", sa.Text(), nullable=True),
        sa.Column("expression", sa.String(), nullable=True),
        sa.Column("triggered_lorebook_json", sa.Text(), nullable=True),
        sa.Column("rejected_patch_json", sa.Text(), nullable=True),
        sa.Column("parser_errors_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_turn_snapshot_message"),
    )
    op.create_index("ix_turn_snapshots_message_id", "turn_snapshots", ["message_id"], unique=False)
    op.create_index("ix_turn_snapshots_session_id", "turn_snapshots", ["session_id"], unique=False)


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def _add_legacy_columns() -> None:
    tables = _table_names()
    if "messages" in tables:
        columns = _column_names("messages")
        additions = (
            ("generation_status", sa.Column("generation_status", sa.String(), server_default="complete", nullable=True)),
            ("segments_json", sa.Column("segments_json", sa.Text(), server_default="[]", nullable=True)),
            ("artifacts_json", sa.Column("artifacts_json", sa.Text(), server_default="[]", nullable=True)),
            ("speaker_metadata_json", sa.Column("speaker_metadata_json", sa.Text(), server_default="{}", nullable=True)),
            ("render_version", sa.Column("render_version", sa.Integer(), server_default="2", nullable=True)),
        )
        for name, column in additions:
            if name not in columns:
                op.add_column("messages", column)

    if "chat_sessions" in tables:
        columns = _column_names("chat_sessions")
        if "persona_id" not in columns:
            op.add_column("chat_sessions", sa.Column("persona_id", sa.String(), nullable=True))
        if "group_id" not in columns:
            op.add_column("chat_sessions", sa.Column("group_id", sa.String(), nullable=True))


def _has_index_columns(table_name: str, columns: tuple[str, ...], *, unique: bool | None = None) -> bool:
    inspector = inspect(op.get_bind())
    candidates = list(inspector.get_indexes(table_name))
    if unique:
        candidates.extend(inspector.get_unique_constraints(table_name))
    for candidate in candidates:
        candidate_columns = tuple(candidate.get("column_names") or ())
        if candidate_columns == columns and (unique is None or bool(candidate.get("unique", unique)) == unique):
            return True
    return False


def _ensure_legacy_indexes() -> None:
    tables = _table_names()
    if "messages" in tables and not _has_index_columns("messages", ("session_id", "sequence"), unique=True):
        connection = op.get_bind()
        rows = connection.execute(
            sa.text(
                "SELECT id, session_id FROM messages "
                "ORDER BY session_id, COALESCE(sequence, 0), COALESCE(created_at, ''), id"
            )
        ).all()
        next_sequence: dict[str, int] = {}
        for message_id, session_id in rows:
            sequence = next_sequence.get(session_id, 0)
            connection.execute(
                sa.text("UPDATE messages SET sequence = :sequence WHERE id = :message_id"),
                {"sequence": sequence, "message_id": message_id},
            )
            next_sequence[session_id] = sequence + 1
        op.create_index(
            "uq_message_session_sequence",
            "messages",
            ["session_id", "sequence"],
            unique=True,
        )

    if "memories" in tables and not _has_index_columns("memories", ("session_id",)):
        op.create_index("ix_memories_session_id", "memories", ["session_id"], unique=False)


def upgrade() -> None:
    _create_if_missing("app_settings", _create_app_settings)
    _create_if_missing("character_groups", _create_character_groups)
    _create_if_missing("characters", _create_characters)
    _create_if_missing("personas", _create_personas)
    _create_if_missing("chat_sessions", _create_chat_sessions)
    _create_if_missing("group_members", _create_group_members)
    _create_if_missing("memories", _create_memories)
    _create_if_missing("messages", _create_messages)
    _create_if_missing("session_branches", _create_session_branches)
    _create_if_missing("session_states", _create_session_states)
    _create_if_missing("turn_snapshots", _create_turn_snapshots)
    _add_legacy_columns()
    _ensure_legacy_indexes()


def downgrade() -> None:
    raise RuntimeError(
        "The initial schema baseline cannot be downgraded because that would delete all user data. "
        "Restore a database backup instead."
    )
