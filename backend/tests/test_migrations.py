from __future__ import annotations

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings
from app.db import models  # noqa: F401
from app.db.migrations import (
    get_database_revision,
    get_head_revision,
    upgrade_database,
    validate_database_schema,
)
from app.db.session import Base, init_db


def _engine(path: Path):
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def test_alembic_builds_and_validates_a_fresh_database(tmp_path):
    engine = _engine(tmp_path / "fresh.db")

    revision = upgrade_database(engine)
    validation = validate_database_schema(engine)

    assert revision == get_head_revision() == "20260720_0003"
    assert validation.revision == validation.head_revision
    assert validation.table_count == len(Base.metadata.tables)
    assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())

    # A second upgrade is a no-op and must remain safe.
    assert upgrade_database(engine) == revision
    engine.dispose()


def test_alembic_adopts_current_unversioned_database_without_data_loss(tmp_path):
    engine = _engine(tmp_path / "unversioned.db")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO characters "
                "(id, name, description, personality, scenario, first_message, normalized_json, raw_json, avatar_path) "
                "VALUES ('legacy-character', '旧角色', '', '', '', '', '{}', '{}', '')"
            )
        )

    assert "alembic_version" not in inspect(engine).get_table_names()

    upgrade_database(engine)
    validate_database_schema(engine)

    with engine.connect() as connection:
        name = connection.execute(
            text("SELECT name FROM characters WHERE id='legacy-character'")
        ).scalar_one()
    assert name == "旧角色"
    assert get_database_revision(engine) == get_head_revision()
    engine.dispose()


def test_initial_revision_repairs_known_legacy_columns_and_sequence_index(tmp_path):
    engine = _engine(tmp_path / "legacy.db")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE chat_sessions ("
                "id TEXT PRIMARY KEY, character_id TEXT NOT NULL, title TEXT, "
                "created_at DATETIME, updated_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE messages ("
                "id TEXT PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL, "
                "content TEXT, sequence INTEGER, created_at DATETIME, updated_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO messages (id, session_id, role, sequence) VALUES "
                "('a', 's1', 'user', 0), ('b', 's1', 'assistant', 0)"
            )
        )

    upgrade_database(engine)

    inspector = inspect(engine)
    message_columns = {column["name"] for column in inspector.get_columns("messages")}
    session_columns = {column["name"] for column in inspector.get_columns("chat_sessions")}
    assert {
        "generation_status",
        "segments_json",
        "artifacts_json",
        "speaker_metadata_json",
        "render_version",
    } <= message_columns
    assert {"persona_id", "group_id"} <= session_columns

    with engine.connect() as connection:
        sequences = connection.execute(
            text("SELECT sequence FROM messages WHERE session_id='s1' ORDER BY sequence")
        ).scalars().all()
    assert sequences == [0, 1]
    engine.dispose()


def test_fresh_migration_has_no_model_schema_drift(tmp_path):
    engine = _engine(tmp_path / "drift.db")
    upgrade_database(engine)

    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={
                "compare_type": True,
                "compare_server_default": False,
                "target_metadata": Base.metadata,
            },
        )
        differences = compare_metadata(context, Base.metadata)

    assert differences == []
    engine.dispose()


def test_init_db_restores_backup_when_migration_fails(tmp_path, monkeypatch):
    database_path = tmp_path / "restore.db"
    backup_dir = tmp_path / "backups"
    engine = _engine(database_path)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE marker (value TEXT NOT NULL)"))
        connection.execute(text("INSERT INTO marker (value) VALUES ('safe')"))

    monkeypatch.setattr(settings, "backups_dir", backup_dir)

    def fail_after_partial_change(target_engine, revision="head"):
        with target_engine.begin() as connection:
            connection.execute(text("CREATE TABLE incomplete_change (id INTEGER)"))
        raise RuntimeError("forced migration failure")

    monkeypatch.setattr("app.db.migrations.upgrade_database", fail_after_partial_change)

    with pytest.raises(RuntimeError, match="forced migration failure"):
        init_db(engine)

    restored_engine = _engine(database_path)
    restored_tables = set(inspect(restored_engine).get_table_names())
    with restored_engine.connect() as connection:
        marker = connection.execute(text("SELECT value FROM marker")).scalar_one()

    assert marker == "safe"
    assert "incomplete_change" not in restored_tables
    assert list(backup_dir.glob("ai_tavern_backup_*.db"))
    restored_engine.dispose()
