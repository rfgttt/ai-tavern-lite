from __future__ import annotations

from contextlib import closing
from datetime import datetime
from pathlib import Path
import shutil
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from ..core.config import settings
from ..core.logging import logger
from .storage_guard import finalize_storage_identity, prepare_storage
from ..services.backup.service import commit_pending_restore, rollback_pending_restore

Base = declarative_base()

storage_preflight = prepare_storage(settings)

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


def _sqlite_database_path(target_engine: Engine = engine) -> Path | None:
    url = make_url(target_engine.url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None

    db_file = Path(url.database)
    if not db_file.is_absolute():
        db_file = (Path.cwd() / db_file).resolve()
    return db_file


def backup_database(target_engine: Engine = engine) -> Path | None:
    """Create a transaction-consistent SQLite backup before migration."""
    db_file = _sqlite_database_path(target_engine)
    if db_file is None or not db_file.exists():
        return None

    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = settings.backups_dir / f"ai_tavern_backup_{timestamp}.db"

    try:
        with closing(sqlite3.connect(str(db_file), timeout=30)) as source:
            with closing(sqlite3.connect(str(backup_path), timeout=30)) as destination:
                source.backup(destination)
                destination.commit()
        logger.info("Database backup created: %s", backup_path)
    except Exception as error:
        backup_path.unlink(missing_ok=True)
        raise RuntimeError(f"Database backup failed; migration was not started: {error}") from error

    try:
        backups = sorted(settings.backups_dir.glob("ai_tavern_backup_*.db"))
        for old_backup in backups[:-5]:
            old_backup.unlink(missing_ok=True)
            logger.info("Old backup removed: %s", old_backup)
    except Exception as error:
        logger.warning("Old database backup cleanup failed: %s", error)

    return backup_path


def _restore_database_after_failed_migration(
    *,
    target_engine: Engine,
    database_path: Path | None,
    backup_path: Path | None,
    database_existed: bool,
) -> None:
    if database_path is None:
        return

    target_engine.dispose()
    for sidecar in (
        Path(f"{database_path}-wal"),
        Path(f"{database_path}-shm"),
    ):
        sidecar.unlink(missing_ok=True)

    if backup_path is not None and backup_path.exists():
        database_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, database_path)
        logger.error("Database restored from backup after migration failure: %s", backup_path)
    elif not database_existed:
        database_path.unlink(missing_ok=True)
        logger.error("Incomplete new database removed after migration failure: %s", database_path)
    else:
        logger.critical(
            "Database migration failed and no usable backup was available: %s",
            database_path,
        )


def migrate_sqlite_schema(target_engine: Engine = engine):
    """Compatibility wrapper for old callers; Alembic now owns migrations."""
    from .migrations import upgrade_database

    return upgrade_database(target_engine)


def init_db(target_engine: Engine = engine):
    """Back up, migrate, and validate the configured database."""
    settings.ensure_directories()
    database_path = _sqlite_database_path(target_engine)
    database_existed = bool(database_path and database_path.exists())
    backup_path = backup_database(target_engine)

    try:
        from . import models  # noqa: F401
        from .migrations import upgrade_database, validate_database_schema

        revision = upgrade_database(target_engine)
        validation = validate_database_schema(target_engine)
        storage_status = finalize_storage_identity(target_engine, storage_preflight)
    except Exception:
        if storage_preflight.restore_application is not None:
            target_engine.dispose()
            rollback_pending_restore(storage_preflight.restore_application)
        else:
            _restore_database_after_failed_migration(
                target_engine=target_engine,
                database_path=database_path,
                backup_path=backup_path,
                database_existed=database_existed,
            )
        raise

    if storage_preflight.restore_application is not None:
        commit_pending_restore(storage_preflight.restore_application)

    logger.info(
        "Database initialized successfully revision=%s tables=%s path=%s instance=%s counts=%s",
        revision,
        validation.table_count,
        storage_status.database_path,
        storage_status.database_instance_id[:12] if storage_status.database_instance_id else "unmanaged",
        storage_status.counts,
    )
    return validation
