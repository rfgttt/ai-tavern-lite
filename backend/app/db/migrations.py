from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine


BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
MIGRATIONS_DIR = BACKEND_DIR / "migrations"


class DatabaseSchemaError(RuntimeError):
    """Raised when the migrated database does not match the application model."""


@dataclass(frozen=True)
class SchemaValidationResult:
    revision: str | None
    head_revision: str
    table_count: int


def _escaped_url(engine: Engine) -> str:
    return engine.url.render_as_string(hide_password=False).replace("%", "%%")


def alembic_config(engine: Engine | None = None) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    if engine is not None:
        config.set_main_option("sqlalchemy.url", _escaped_url(engine))
    return config


def get_head_revision() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def get_database_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def upgrade_database(engine: Engine, revision: str = "head") -> str | None:
    config = alembic_config(engine)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
    return get_database_revision(engine)


def validate_database_schema(engine: Engine) -> SchemaValidationResult:
    from .session import Base
    from . import models  # noqa: F401

    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables)
    missing_tables = sorted(expected_tables - actual_tables)

    missing_columns: list[str] = []
    for table_name in sorted(expected_tables & actual_tables):
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        expected_columns = set(Base.metadata.tables[table_name].columns.keys())
        for column_name in sorted(expected_columns - actual_columns):
            missing_columns.append(f"{table_name}.{column_name}")

    index_errors: list[str] = []
    if "messages" in actual_tables:
        candidates = [*inspector.get_indexes("messages"), *inspector.get_unique_constraints("messages")]
        has_sequence_unique = any(
            tuple(item.get("column_names") or ()) == ("session_id", "sequence")
            and bool(item.get("unique", True))
            for item in candidates
        )
        if not has_sequence_unique:
            index_errors.append("messages(session_id, sequence) unique")

    if "memories" in actual_tables:
        has_session_index = any(
            tuple(item.get("column_names") or ()) == ("session_id",)
            for item in inspector.get_indexes("memories")
        )
        if not has_session_index:
            index_errors.append("memories(session_id) index")

    revision = get_database_revision(engine)
    head = get_head_revision()
    problems: list[str] = []
    if revision != head:
        problems.append(f"database revision is {revision!r}, expected {head!r}")
    if missing_tables:
        problems.append("missing tables: " + ", ".join(missing_tables))
    if missing_columns:
        problems.append("missing columns: " + ", ".join(missing_columns))
    if index_errors:
        problems.append("missing indexes: " + ", ".join(index_errors))
    if problems:
        raise DatabaseSchemaError("; ".join(problems))

    return SchemaValidationResult(
        revision=revision,
        head_revision=head,
        table_count=len(expected_tables),
    )
