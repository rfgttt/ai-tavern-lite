from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from ..core.config import settings
from ..core.logging import logger
import sqlite3
from datetime import datetime
from pathlib import Path
from sqlalchemy.engine import make_url

Base = declarative_base()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30} if "sqlite" in settings.database_url else {},
    echo=False,
    pool_pre_ping=True,
)


if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def backup_database():
    """Create a transaction-consistent SQLite backup before starting."""
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return

    db_file = Path(url.database)
    if not db_file.is_absolute():
        db_file = (Path.cwd() / db_file).resolve()
    if not db_file.exists():
        return

    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = settings.backups_dir / f"ai_tavern_backup_{timestamp}.db"

    try:
        with sqlite3.connect(str(db_file), timeout=30) as source:
            with sqlite3.connect(str(backup_path), timeout=30) as destination:
                source.backup(destination)
        logger.info("Database backup created: %s", backup_path)

        backups = sorted(settings.backups_dir.glob("ai_tavern_backup_*.db"))
        for old_backup in backups[:-5]:
            old_backup.unlink(missing_ok=True)
            logger.info("Old backup removed: %s", old_backup)
    except Exception as error:
        backup_path.unlink(missing_ok=True)
        logger.warning("Database backup failed: %s", error)



def migrate_sqlite_schema(target_engine=engine):
    """Apply safe, idempotent migrations that create_all cannot add to old SQLite DBs."""
    if target_engine.dialect.name != "sqlite":
        return

    with target_engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())

        if "messages" in tables:
            message_columns = {item["name"] for item in inspector.get_columns("messages")}
            for column_name, ddl in (
                ("segments_json", "TEXT DEFAULT '[]'"),
                ("artifacts_json", "TEXT DEFAULT '[]'"),
                ("speaker_metadata_json", "TEXT DEFAULT '{}'"),
                ("render_version", "INTEGER DEFAULT 2"),
            ):
                if column_name not in message_columns:
                    connection.execute(text(f"ALTER TABLE messages ADD COLUMN {column_name} {ddl}"))
                    logger.info("Migrated messages.%s", column_name)

            unique_constraints = inspector.get_unique_constraints("messages")
            indexes = inspector.get_indexes("messages")
            has_sequence_uniqueness = any(
                set(item.get("column_names") or []) == {"session_id", "sequence"}
                for item in [*unique_constraints, *indexes]
                if item.get("unique", True)
            )

            if not has_sequence_uniqueness:
                rows = connection.execute(
                    text(
                        "SELECT id, session_id FROM messages "
                        "ORDER BY session_id, sequence, COALESCE(created_at, ''), id"
                    )
                ).all()
                next_sequence: dict[str, int] = {}
                for message_id, session_id in rows:
                    sequence = next_sequence.get(session_id, 0)
                    connection.execute(
                        text("UPDATE messages SET sequence = :sequence WHERE id = :message_id"),
                        {"sequence": sequence, "message_id": message_id},
                    )
                    next_sequence[session_id] = sequence + 1

                connection.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_message_session_sequence "
                        "ON messages (session_id, sequence)"
                    )
                )
                logger.info("Migrated message sequence uniqueness")

        if "chat_sessions" in tables:
            session_columns = {item["name"] for item in inspector.get_columns("chat_sessions")}
            for column_name in ("persona_id", "group_id"):
                if column_name not in session_columns:
                    connection.execute(text(f"ALTER TABLE chat_sessions ADD COLUMN {column_name} VARCHAR"))
                    logger.info("Migrated chat_sessions.%s", column_name)

        if "memories" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_memories_session_id "
                    "ON memories (session_id)"
                )
            )

def init_db():
    """Initialize database and create tables."""
    settings.ensure_directories()
    backup_database()

    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    migrate_sqlite_schema(engine)
    logger.info("Database initialized successfully")
