from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url

from ..core.logging import logger
from ..services.backup.service import RestoreApplication, apply_pending_restore


REGISTRY_FORMAT_VERSION = 1
INSTANCE_SETTING_KEY = "database_instance_id"
_MANAGED_ASSET_DIRS = ("avatars", "characters", "exports")
_COUNT_TABLES = {
    "characters": "characters",
    "sessions": "chat_sessions",
    "messages": "messages",
    "memories": "memories",
    "personas": "personas",
    "groups": "character_groups",
}


class StorageGuardError(RuntimeError):
    """Raised when managed storage identity cannot be verified safely."""


@dataclass(frozen=True)
class StoragePreflight:
    managed: bool
    database_path: Path | None
    registry_path: Path | None
    registry: dict[str, Any] | None = None
    adopted_from: str | None = None
    first_run: bool = False
    restore_application: RestoreApplication | None = None


@dataclass
class StorageStatus:
    managed: bool = False
    database_path: str = ""
    registry_path: str = ""
    database_instance_id: str = ""
    alembic_revision: str | None = None
    integrity: str = "unknown"
    adopted_from: str | None = None
    counts: dict[str, int] = field(default_factory=dict)
    previous_counts: dict[str, int] = field(default_factory=dict)
    count_regressions: dict[str, dict[str, int]] = field(default_factory=dict)


_current_status = StorageStatus()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalized_path(path: Path) -> str:
    resolved = str(path.expanduser().resolve(strict=False))
    return os.path.normcase(resolved)


def _database_path_from_url(database_url: str) -> Path | None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    path = Path(url.database).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve(strict=False)
    return path


def _read_registry(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StorageGuardError(
            f"Storage registry is unreadable: {path}. Refusing to guess which database to use."
        ) from error
    if not isinstance(payload, dict) or payload.get("format_version") != REGISTRY_FORMAT_VERSION:
        raise StorageGuardError(
            f"Storage registry has an unsupported format: {path}. Refusing to start."
        )
    return payload


def _write_registry(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _open_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise StorageGuardError(f"Database file does not exist: {path}")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=30)


def _validate_sqlite_file(path: Path) -> None:
    try:
        with closing(_open_readonly(path)) as connection:
            integrity_rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check")]
            if integrity_rows != ["ok"]:
                raise StorageGuardError(
                    f"SQLite integrity check failed for {path}: {'; '.join(integrity_rows[:5])}"
                )
            foreign_key_issues = list(connection.execute("PRAGMA foreign_key_check"))
            if foreign_key_issues:
                raise StorageGuardError(
                    f"SQLite foreign-key check found {len(foreign_key_issues)} issue(s) in {path}."
                )
    except StorageGuardError:
        raise
    except sqlite3.Error as error:
        raise StorageGuardError(f"Database cannot be opened safely: {path}: {error}") from error


def _read_instance_id_from_file(path: Path) -> str | None:
    try:
        with closing(_open_readonly(path)) as connection:
            has_settings = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_settings'"
            ).fetchone()
            if not has_settings:
                return None
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key=?",
                (INSTANCE_SETTING_KEY,),
            ).fetchone()
            return str(row[0]).strip() if row and row[0] else None
    except sqlite3.Error as error:
        raise StorageGuardError(f"Could not read database identity from {path}: {error}") from error


def _copy_sqlite_database(source_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination_path.with_name(f".{destination_path.name}.{uuid4().hex}.tmp")
    try:
        with closing(sqlite3.connect(str(source_path), timeout=30)) as source:
            with closing(sqlite3.connect(str(temp_path), timeout=30)) as destination:
                source.backup(destination)
                destination.commit()
        _validate_sqlite_file(temp_path)
        os.replace(temp_path, destination_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _copy_legacy_assets(legacy_data_dir: Path, managed_data_dir: Path) -> None:
    for directory_name in _MANAGED_ASSET_DIRS:
        source = legacy_data_dir / directory_name
        destination = managed_data_dir / directory_name
        if not source.exists() or not source.is_dir():
            continue
        shutil.copytree(source, destination, dirs_exist_ok=True)


def prepare_storage(runtime_settings: Any) -> StoragePreflight:
    """Resolve and validate managed storage before SQLAlchemy opens the database."""
    database_path = _database_path_from_url(runtime_settings.database_url)
    managed = bool(runtime_settings.uses_managed_storage and database_path is not None)
    registry_path = Path(runtime_settings.storage_registry_path).expanduser() if managed else None

    if not managed:
        logger.info(
            "Storage guard bypassed for explicit or non-SQLite database: %s",
            database_path or runtime_settings.database_url,
        )
        return StoragePreflight(
            managed=False,
            database_path=database_path,
            registry_path=None,
        )

    assert database_path is not None
    assert registry_path is not None
    registry = _read_registry(registry_path)

    if registry is not None:
        expected_path_raw = str(registry.get("database_path", "")).strip()
        if not expected_path_raw:
            raise StorageGuardError(f"Storage registry does not contain a database path: {registry_path}")
        expected_path = Path(expected_path_raw).expanduser()
        if _normalized_path(expected_path) != _normalized_path(database_path):
            raise StorageGuardError(
                "Managed database path does not match the registered storage identity. "
                f"Registered: {expected_path}; configured: {database_path}. "
                "The application will not silently switch databases."
            )
        if not database_path.exists():
            raise StorageGuardError(
                "The registered AI Tavern database is missing. "
                f"Expected: {database_path}. No replacement database was created."
            )
        _validate_sqlite_file(database_path)
        registered_id = str(registry.get("database_instance_id", "")).strip()
        actual_id = _read_instance_id_from_file(database_path)
        if not registered_id or not actual_id or registered_id != actual_id:
            raise StorageGuardError(
                "The database file does not match the registered storage identity. "
                f"Database: {database_path}. No data was modified."
            )

        restore_application = apply_pending_restore(
            data_dir=Path(runtime_settings.data_dir).expanduser(),
            backups_dir=Path(getattr(runtime_settings, "backups_dir", Path(runtime_settings.data_dir) / "backups")).expanduser(),
            database_path=database_path,
            registry=registry,
        )
        if restore_application is not None:
            try:
                _validate_sqlite_file(database_path)
                restored_id = _read_instance_id_from_file(database_path)
                if restored_id != registered_id:
                    raise StorageGuardError(
                        "Restored database does not match the registered storage identity. "
                        "The pre-restore safety snapshot was preserved."
                    )
            except Exception:
                from ..services.backup.service import rollback_pending_restore
                rollback_pending_restore(restore_application)
                raise
        return StoragePreflight(
            managed=True,
            database_path=database_path,
            registry_path=registry_path,
            registry=registry,
            first_run=False,
            restore_application=restore_application,
        )

    adopted_from: str | None = None
    first_run = not database_path.exists()
    legacy_data_dir = Path(runtime_settings.legacy_data_dir).expanduser()
    legacy_database = legacy_data_dir / "ai_tavern.db"

    if database_path.exists() and legacy_database.exists():
        raise StorageGuardError(
            "Two unregistered AI Tavern databases were found, so the application cannot safely choose one. "
            f"Managed candidate: {database_path}; project-local candidate: {legacy_database}. "
            "No database was modified. Restore the storage registry or resolve the duplicate files explicitly."
        )

    if not database_path.exists() and legacy_database.exists():
        _validate_sqlite_file(legacy_database)
        _copy_sqlite_database(legacy_database, database_path)
        _copy_legacy_assets(legacy_data_dir, Path(runtime_settings.data_dir))
        adopted_from = str(legacy_database.resolve(strict=False))
        first_run = False
        logger.warning(
            "Adopted legacy project-local database into managed storage; source was preserved: %s -> %s",
            legacy_database,
            database_path,
        )
    elif database_path.exists():
        _validate_sqlite_file(database_path)

    return StoragePreflight(
        managed=True,
        database_path=database_path,
        registry_path=registry_path,
        registry=None,
        adopted_from=adopted_from,
        first_run=first_run,
    )


def _database_counts(target_engine: Engine) -> dict[str, int]:
    counts: dict[str, int] = {}
    with target_engine.connect() as connection:
        table_names = {
            str(row[0])
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        for label, table_name in _COUNT_TABLES.items():
            if table_name in table_names:
                counts[label] = int(connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())
            else:
                counts[label] = 0
    return counts


def _database_revision(target_engine: Engine) -> str | None:
    with target_engine.connect() as connection:
        table_exists = connection.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        ).first()
        if not table_exists:
            return None
        return connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()


def _ensure_instance_id(target_engine: Engine) -> str:
    with target_engine.begin() as connection:
        existing = connection.execute(
            text("SELECT value FROM app_settings WHERE key=:key"),
            {"key": INSTANCE_SETTING_KEY},
        ).scalar_one_or_none()
        if existing and str(existing).strip():
            return str(existing).strip()
        instance_id = str(uuid4())
        connection.execute(
            text("INSERT INTO app_settings (key, value) VALUES (:key, :value)"),
            {"key": INSTANCE_SETTING_KEY, "value": instance_id},
        )
        return instance_id


def finalize_storage_identity(
    target_engine: Engine,
    preflight: StoragePreflight,
) -> StorageStatus:
    """Bind the migrated database to its registry and publish safe diagnostics."""
    global _current_status

    if not preflight.managed:
        counts = _database_counts(target_engine) if target_engine.dialect.name == "sqlite" else {}
        _current_status = StorageStatus(
            managed=False,
            database_path=str(preflight.database_path or target_engine.url),
            counts=counts,
        )
        return _current_status

    assert preflight.database_path is not None
    assert preflight.registry_path is not None
    instance_id = _ensure_instance_id(target_engine)
    if preflight.registry is not None:
        registered_id = str(preflight.registry.get("database_instance_id", "")).strip()
        if instance_id != registered_id:
            raise StorageGuardError(
                "Database identity changed during startup. Refusing to update the storage registry."
            )

    _validate_sqlite_file(preflight.database_path)
    counts = _database_counts(target_engine)
    previous_counts = dict((preflight.registry or {}).get("counts") or {})
    regressions = {
        key: {"previous": int(previous_counts[key]), "current": int(current)}
        for key, current in counts.items()
        if key in previous_counts and int(current) < int(previous_counts[key])
    }
    revision = _database_revision(target_engine)
    existing_created_at = (preflight.registry or {}).get("created_at")
    payload = {
        "format_version": REGISTRY_FORMAT_VERSION,
        "database_path": str(preflight.database_path.resolve(strict=False)),
        "database_instance_id": instance_id,
        "created_at": existing_created_at or _utc_now(),
        "last_verified_at": _utc_now(),
        "alembic_revision": revision,
        "counts": counts,
        "adopted_from": (preflight.registry or {}).get("adopted_from") or preflight.adopted_from,
    }
    _write_registry(preflight.registry_path, payload)

    if regressions:
        logger.warning("Managed storage counts decreased since the previous verified startup: %s", regressions)

    _current_status = StorageStatus(
        managed=True,
        database_path=str(preflight.database_path.resolve(strict=False)),
        registry_path=str(preflight.registry_path.resolve(strict=False)),
        database_instance_id=instance_id,
        alembic_revision=revision,
        integrity="ok",
        adopted_from=payload.get("adopted_from"),
        counts=counts,
        previous_counts={key: int(value) for key, value in previous_counts.items()},
        count_regressions=regressions,
    )
    return _current_status


def get_storage_status() -> dict[str, Any]:
    return asdict(_current_status)
