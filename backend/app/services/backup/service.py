from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile
from typing import Any, Iterable
from uuid import uuid4
import zipfile

from ...core.logging import logger


BACKUP_FORMAT = "ai-tavern-backup"
BACKUP_FORMAT_VERSION = 1
APP_VERSION = "2.2.0-preview.1"
PENDING_FORMAT_VERSION = 1
DATABASE_ARCHIVE_PATH = "database.sqlite3"
MANIFEST_ARCHIVE_PATH = "manifest.json"
PENDING_MARKER_NAME = "pending-restore.json"
STAGING_DIRECTORY_NAME = "restore-staging"
INSTANCE_SETTING_KEY = "database_instance_id"
ASSET_DIRECTORIES = ("avatars", "characters")
ALLOWED_ASSET_SUFFIXES = {
    "avatars": {".png", ".jpg", ".jpeg", ".webp", ".gif"},
    "characters": {".json", ".png"},
}
IGNORED_ASSET_PLACEHOLDERS = {".gitkeep"}
COUNT_TABLES = {
    "characters": "characters",
    "sessions": "chat_sessions",
    "messages": "messages",
    "session_states": "session_states",
    "turn_snapshots": "turn_snapshots",
    "memories": "memories",
    "personas": "personas",
    "groups": "character_groups",
    "group_members": "group_members",
    "branches": "session_branches",
    "state_aliases": "character_state_aliases",
}
REQUIRED_SCHEMA = {
    "characters": {"id", "name", "normalized_json", "raw_json", "avatar_path"},
    "chat_sessions": {"id", "character_id", "persona_id", "group_id"},
    "messages": {"id", "session_id", "role", "content", "sequence"},
    "session_states": {"session_id", "state_json", "revision"},
    "turn_snapshots": {"id", "session_id", "message_id", "state_after_json"},
    "memories": {"id", "character_id", "session_id", "category", "content"},
    "app_settings": {"key", "value"},
    "personas": {"id", "name", "description"},
    "character_groups": {"id", "name"},
    "group_members": {"id", "group_id", "character_id"},
    "session_branches": {"id", "session_id", "messages_json", "runtime_state_json"},
    "character_state_aliases": {
        "id", "character_id", "alias", "alias_key", "semantic",
        "canonical_path", "source", "confidence",
    },
    "alembic_version": {"version_num"},
}
EXACT_SENSITIVE_SETTING_KEYS = {
    "api_key",
    "custom_headers",
    INSTANCE_SETTING_KEY,
}
SENSITIVE_KEY_MARKERS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "access_token",
    "refresh_token",
    "authorization",
    "auth_header",
    "private_key",
)


class BackupError(RuntimeError):
    """Raised when a backup cannot be created, validated, staged, or applied safely."""


@dataclass(frozen=True)
class BackupExport:
    archive_path: Path
    cleanup_root: Path
    filename: str
    manifest: dict[str, Any]


@dataclass
class RestoreApplication:
    restore_id: str
    marker_path: Path
    staging_dir: Path
    safety_dir: Path
    database_path: Path
    old_asset_dirs: dict[str, Path]
    summary: dict[str, Any]
    finalized: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalized_path(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sensitive_setting_key(key: str) -> bool:
    normalized = str(key or "").strip().lower()
    return normalized in EXACT_SENSITIVE_SETTING_KEYS or any(
        marker in normalized for marker in SENSITIVE_KEY_MARKERS
    )


def _open_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise BackupError(f"数据库文件不存在：{path}")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=30)


def _copy_sqlite_database(source_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination_path.with_name(f".{destination_path.name}.{uuid4().hex}.tmp")
    try:
        with closing(sqlite3.connect(str(source_path), timeout=30)) as source:
            with closing(sqlite3.connect(str(temp_path), timeout=30)) as destination:
                source.backup(destination)
                destination.commit()
        _validate_database(temp_path)
        os.replace(temp_path, destination_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _remove_sqlite_sidecars(database_path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        Path(f"{database_path}{suffix}").unlink(missing_ok=True)


def _copy_static_database(source_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination_path.with_name(f".{destination_path.name}.{uuid4().hex}.tmp")
    try:
        shutil.copy2(source_path, temp_path)
        _validate_database(temp_path)
        _remove_sqlite_sidecars(destination_path)
        os.replace(temp_path, destination_path)
        _remove_sqlite_sidecars(destination_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _database_revision(connection: sqlite3.Connection) -> str | None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
    ).fetchone()
    if not exists:
        return None
    row = connection.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
    return str(row[0]) if row and row[0] else None


def _database_counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    return {
        label: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        if table in tables else 0
        for label, table in COUNT_TABLES.items()
    }


def _validate_database(path: Path, *, expected_revision: str | None = None) -> dict[str, Any]:
    try:
        with closing(_open_readonly(path)) as connection:
            integrity = [str(row[0]) for row in connection.execute("PRAGMA integrity_check")]
            if integrity != ["ok"]:
                raise BackupError(
                    f"SQLite 完整性检查失败：{'；'.join(integrity[:5])}"
                )
            foreign_keys = list(connection.execute("PRAGMA foreign_key_check"))
            if foreign_keys:
                raise BackupError(f"数据库存在 {len(foreign_keys)} 个外键问题")

            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            missing_tables = sorted(set(REQUIRED_SCHEMA) - tables)
            unexpected_tables = sorted(
                table for table in tables
                if table not in REQUIRED_SCHEMA and not table.startswith("sqlite_")
            )
            unexpected_objects = [
                f"{row[0]}:{row[1]}"
                for row in connection.execute(
                    "SELECT type, name FROM sqlite_master "
                    "WHERE type IN ('trigger', 'view') AND name NOT LIKE 'sqlite_%'"
                )
            ]
            missing_columns: list[str] = []
            for table_name, expected_columns in REQUIRED_SCHEMA.items():
                if table_name not in tables:
                    continue
                actual_columns = {
                    str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table_name}")')
                }
                missing_columns.extend(
                    f"{table_name}.{column}"
                    for column in sorted(expected_columns - actual_columns)
                )
            revision = _database_revision(connection)
            if expected_revision is not None and revision != expected_revision:
                raise BackupError(
                    f"数据库版本不兼容：备份为 {revision or 'unknown'}，当前要求 {expected_revision}"
                )
            if missing_tables or unexpected_tables or unexpected_objects or missing_columns:
                details = []
                if missing_tables:
                    details.append("缺少表：" + "、".join(missing_tables))
                if unexpected_tables:
                    details.append("包含未知表：" + "、".join(unexpected_tables))
                if unexpected_objects:
                    details.append("包含不允许的触发器或视图：" + "、".join(unexpected_objects))
                if missing_columns:
                    details.append("缺少字段：" + "、".join(missing_columns))
                raise BackupError("；".join(details))
            return {
                "revision": revision,
                "counts": _database_counts(connection),
                "integrity": "ok",
                "foreign_key_issues": 0,
            }
    except BackupError:
        raise
    except sqlite3.Error as error:
        raise BackupError(f"数据库无法安全读取：{error}") from error


def _read_settings(path: Path, *, sensitive_only: bool = False) -> dict[str, str]:
    with closing(_open_readonly(path)) as connection:
        has_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_settings'"
        ).fetchone()
        if not has_table:
            return {}
        rows = connection.execute("SELECT key, value FROM app_settings").fetchall()
    result = {str(key): str(value or "") for key, value in rows}
    if sensitive_only:
        return {key: value for key, value in result.items() if _is_sensitive_setting_key(key)}
    return result


def _sanitize_portable_database(path: Path) -> list[str]:
    removed: list[str] = []
    with closing(sqlite3.connect(str(path), timeout=30)) as connection:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_settings'"
        ).fetchone()
        if table_exists:
            keys = [str(row[0]) for row in connection.execute("SELECT key FROM app_settings")]
            removed = sorted(key for key in keys if _is_sensitive_setting_key(key))
            if removed:
                connection.executemany(
                    "DELETE FROM app_settings WHERE key=?",
                    [(key,) for key in removed],
                )
                connection.commit()
        connection.execute("VACUUM")
    return removed


def _inject_local_settings(
    path: Path,
    *,
    preserved_settings: dict[str, str],
    database_instance_id: str,
) -> None:
    safe_settings = {
        str(key): str(value)
        for key, value in preserved_settings.items()
        if _is_sensitive_setting_key(key) and key != INSTANCE_SETTING_KEY
    }
    safe_settings[INSTANCE_SETTING_KEY] = database_instance_id
    with closing(sqlite3.connect(str(path), timeout=30)) as connection:
        keys = [str(row[0]) for row in connection.execute("SELECT key FROM app_settings")]
        sensitive_existing = [key for key in keys if _is_sensitive_setting_key(key)]
        if sensitive_existing:
            connection.executemany(
                "DELETE FROM app_settings WHERE key=?",
                [(key,) for key in sensitive_existing],
            )
        connection.executemany(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            list(safe_settings.items()),
        )
        connection.commit()
        connection.execute("VACUUM")


def _safe_asset_files(directory: Path, directory_name: str) -> Iterable[tuple[Path, str]]:
    if not directory.exists():
        return []
    allowed_suffixes = ALLOWED_ASSET_SUFFIXES[directory_name]
    files: list[tuple[Path, str]] = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise BackupError(f"资产目录包含符号链接，已拒绝备份：{path}")
        if not path.is_file():
            continue
        if path.name.lower() in IGNORED_ASSET_PLACEHOLDERS:
            continue
        if path.suffix.lower() not in allowed_suffixes:
            raise BackupError(f"资产文件类型不受支持：{path.name}")
        relative = path.relative_to(directory).as_posix()
        files.append((path, relative))
    return files


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _manifest_database_entry(database_path: Path, validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": DATABASE_ARCHIVE_PATH,
        "size": database_path.stat().st_size,
        "sha256": _sha256_file(database_path),
        "alembic_revision": validation["revision"],
        "counts": validation["counts"],
    }


def build_backup_archive(
    *,
    database_path: Path,
    avatars_dir: Path,
    characters_dir: Path,
    exports_dir: Path,
    max_uncompressed_bytes: int,
) -> BackupExport:
    """Create a portable, secret-free ZIP without modifying the live database."""
    if not database_path.exists():
        raise BackupError(f"当前数据库不存在：{database_path}")

    exports_dir.mkdir(parents=True, exist_ok=True)
    cleanup_root = Path(tempfile.mkdtemp(prefix="backup-export-", dir=str(exports_dir)))
    snapshot_path = cleanup_root / DATABASE_ARCHIVE_PATH
    archive_path = cleanup_root / "backup.zip"
    try:
        _copy_sqlite_database(database_path, snapshot_path)
        removed_settings = _sanitize_portable_database(snapshot_path)
        excluded_settings = sorted(set(removed_settings) | EXACT_SENSITIVE_SETTING_KEYS)
        validation = _validate_database(snapshot_path)

        assets: list[dict[str, Any]] = []
        total_uncompressed = snapshot_path.stat().st_size
        asset_sources: list[tuple[Path, str]] = []
        for directory_name, source_dir in (
            ("avatars", avatars_dir),
            ("characters", characters_dir),
        ):
            for source_path, relative in _safe_asset_files(source_dir, directory_name):
                archive_name = f"assets/{directory_name}/{relative}"
                size = source_path.stat().st_size
                total_uncompressed += size
                if total_uncompressed > max_uncompressed_bytes:
                    raise BackupError("备份内容超过允许的未压缩大小")
                assets.append({
                    "path": archive_name,
                    "size": size,
                    "sha256": _sha256_file(source_path),
                })
                asset_sources.append((source_path, archive_name))

        manifest = {
            "format": BACKUP_FORMAT,
            "format_version": BACKUP_FORMAT_VERSION,
            "app_version": APP_VERSION,
            "created_at": _utc_now(),
            "database": _manifest_database_entry(snapshot_path, validation),
            "assets": assets,
            "excluded_settings": excluded_settings,
            "notes": {
                "portable": True,
                "api_key_included": False,
                "custom_headers_included": False,
                "storage_identity_included": False,
            },
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr(MANIFEST_ARCHIVE_PATH, manifest_bytes)
            archive.write(snapshot_path, DATABASE_ARCHIVE_PATH)
            for source_path, archive_name in asset_sources:
                archive.write(source_path, archive_name)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return BackupExport(
            archive_path=archive_path,
            cleanup_root=cleanup_root,
            filename=f"ai-tavern-backup-{timestamp}.zip",
            manifest=manifest,
        )
    except Exception:
        shutil.rmtree(cleanup_root, ignore_errors=True)
        raise


def _safe_zip_name(name: str) -> str:
    if "\\" in name or "\x00" in name or ":" in name:
        raise BackupError(f"ZIP 路径格式不安全：{name}")
    pure = PurePosixPath(name)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise BackupError(f"ZIP 路径不安全：{name}")
    return pure.as_posix()


def _zip_entry_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return bool(mode and stat.S_ISLNK(mode))


def _validated_zip_entries(
    archive: zipfile.ZipFile,
    *,
    max_entries: int,
    max_uncompressed_bytes: int,
) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > max_entries:
        raise BackupError(f"备份包文件数量过多：{len(infos)}")
    total = 0
    entries: dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        safe_name = _safe_zip_name(info.filename.rstrip("/")) if info.filename.rstrip("/") else ""
        if not safe_name:
            continue
        if _zip_entry_is_symlink(info):
            raise BackupError(f"备份包包含符号链接：{safe_name}")
        if info.flag_bits & 0x1:
            raise BackupError("不支持加密 ZIP")
        if info.is_dir():
            continue
        if safe_name in entries:
            raise BackupError(f"备份包包含重复路径：{safe_name}")
        total += int(info.file_size)
        if total > max_uncompressed_bytes:
            raise BackupError("备份包解压后大小超过安全限制")
        entries[safe_name] = info
    return entries


def _read_manifest(archive: zipfile.ZipFile, entries: dict[str, zipfile.ZipInfo]) -> dict[str, Any]:
    info = entries.get(MANIFEST_ARCHIVE_PATH)
    if info is None:
        raise BackupError("备份包缺少 manifest.json")
    if info.file_size > 1024 * 1024:
        raise BackupError("manifest.json 异常过大")
    try:
        payload = json.loads(archive.read(info).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupError(f"manifest.json 无法解析：{error}") from error
    if not isinstance(payload, dict):
        raise BackupError("manifest.json 必须是 JSON 对象")
    if payload.get("format") != BACKUP_FORMAT:
        raise BackupError("不是 AI Tavern Lite 备份包")
    if payload.get("format_version") != BACKUP_FORMAT_VERSION:
        raise BackupError("备份格式版本不受支持")
    return payload


def _extract_and_hash(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    destination: Path,
) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256()
    size = 0
    with archive.open(info, "r") as source, destination.open("wb") as target:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            target.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _validate_manifest_file(
    *,
    entry: dict[str, Any],
    actual_path: str,
    actual_size: int,
    actual_hash: str,
) -> None:
    if str(entry.get("path", "")) != actual_path:
        raise BackupError(f"manifest 路径不匹配：{actual_path}")
    if int(entry.get("size", -1)) != actual_size:
        raise BackupError(f"文件大小校验失败：{actual_path}")
    if str(entry.get("sha256", "")).lower() != actual_hash.lower():
        raise BackupError(f"SHA-256 校验失败：{actual_path}")


def _pending_marker_path(data_dir: Path) -> Path:
    return data_dir / PENDING_MARKER_NAME


def _load_pending_marker(data_dir: Path) -> dict[str, Any] | None:
    path = _pending_marker_path(data_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BackupError(f"待恢复标记无法读取：{path}") from error
    if not isinstance(payload, dict) or payload.get("format_version") != PENDING_FORMAT_VERSION:
        raise BackupError("待恢复标记格式无效")
    return payload


def _pending_public_payload(marker: dict[str, Any]) -> dict[str, Any]:
    return {
        "restore_id": str(marker.get("restore_id", "")),
        "staged_at": str(marker.get("staged_at", "")),
        "backup_created_at": str(marker.get("backup_created_at", "")),
        "source_app_version": str(marker.get("source_app_version", "")),
        "alembic_revision": str(marker.get("alembic_revision", "")),
        "counts": dict(marker.get("counts") or {}),
        "asset_count": int(marker.get("asset_count", 0)),
        "restart_required": True,
    }


def get_backup_status(*, data_dir: Path, database_path: Path) -> dict[str, Any]:
    current: dict[str, Any] = {
        "database_path": str(database_path.resolve(strict=False)),
        "exists": database_path.exists(),
        "revision": None,
        "counts": {},
        "integrity": "missing",
    }
    if database_path.exists():
        validation = _validate_database(database_path)
        current.update(
            revision=validation["revision"],
            counts=validation["counts"],
            integrity=validation["integrity"],
        )
    marker = _load_pending_marker(data_dir)
    return {
        "format_version": BACKUP_FORMAT_VERSION,
        "current": current,
        "pending_restore": _pending_public_payload(marker) if marker else None,
        "portable_backup_excludes": ["api_key", "custom_headers", "database_instance_id"],
    }


def stage_restore_archive(
    *,
    archive_path: Path,
    data_dir: Path,
    database_path: Path,
    expected_revision: str,
    database_instance_id: str,
    preserved_settings: dict[str, str],
    max_entries: int,
    max_uncompressed_bytes: int,
) -> dict[str, Any]:
    if _load_pending_marker(data_dir) is not None:
        raise BackupError("已有待执行的恢复任务，请先重启完成或取消")
    if not database_instance_id:
        raise BackupError("当前数据库没有有效的存储身份，不能准备恢复")

    restore_id = uuid4().hex
    staging_dir = data_dir / STAGING_DIRECTORY_NAME / restore_id
    staging_database = staging_dir / DATABASE_ARCHIVE_PATH
    marker_path = _pending_marker_path(data_dir)
    try:
        staging_dir.mkdir(parents=True, exist_ok=False)
        for directory_name in ASSET_DIRECTORIES:
            (staging_dir / "assets" / directory_name).mkdir(parents=True, exist_ok=True)

        try:
            archive = zipfile.ZipFile(archive_path, "r")
        except zipfile.BadZipFile as error:
            raise BackupError("上传文件不是有效 ZIP") from error

        with archive:
            entries = _validated_zip_entries(
                archive,
                max_entries=max_entries,
                max_uncompressed_bytes=max_uncompressed_bytes,
            )
            manifest = _read_manifest(archive, entries)
            database_entry = manifest.get("database")
            if not isinstance(database_entry, dict):
                raise BackupError("manifest 缺少数据库信息")
            database_info = entries.get(DATABASE_ARCHIVE_PATH)
            if database_info is None:
                raise BackupError("备份包缺少 database.sqlite3")
            db_size, db_hash = _extract_and_hash(archive, database_info, staging_database)
            _validate_manifest_file(
                entry=database_entry,
                actual_path=DATABASE_ARCHIVE_PATH,
                actual_size=db_size,
                actual_hash=db_hash,
            )

            validation = _validate_database(staging_database, expected_revision=expected_revision)
            manifest_revision = str(database_entry.get("alembic_revision") or "")
            if manifest_revision != expected_revision or validation["revision"] != expected_revision:
                raise BackupError("备份数据库版本与当前应用不一致")
            manifest_counts = database_entry.get("counts")
            if not isinstance(manifest_counts, dict) or {
                key: int(value) for key, value in manifest_counts.items()
            } != validation["counts"]:
                raise BackupError("manifest 中的数据数量与数据库不一致")

            asset_manifest = manifest.get("assets", [])
            if not isinstance(asset_manifest, list):
                raise BackupError("manifest 的 assets 字段无效")
            expected_asset_paths: set[str] = set()
            for raw_entry in asset_manifest:
                if not isinstance(raw_entry, dict):
                    raise BackupError("manifest 资产条目无效")
                asset_path = _safe_zip_name(str(raw_entry.get("path", "")))
                parts = PurePosixPath(asset_path).parts
                if len(parts) < 3 or parts[0] != "assets" or parts[1] not in ASSET_DIRECTORIES:
                    raise BackupError(f"资产路径不受支持：{asset_path}")
                if Path(parts[-1]).suffix.lower() not in ALLOWED_ASSET_SUFFIXES[parts[1]]:
                    raise BackupError(f"资产文件类型不受支持：{asset_path}")
                if asset_path in expected_asset_paths:
                    raise BackupError(f"manifest 包含重复资产：{asset_path}")
                expected_asset_paths.add(asset_path)
                info = entries.get(asset_path)
                if info is None:
                    raise BackupError(f"备份包缺少资产：{asset_path}")
                destination = staging_dir.joinpath(*PurePosixPath(asset_path).parts)
                asset_size, asset_hash = _extract_and_hash(archive, info, destination)
                _validate_manifest_file(
                    entry=raw_entry,
                    actual_path=asset_path,
                    actual_size=asset_size,
                    actual_hash=asset_hash,
                )

            archive_asset_paths = {
                name for name in entries
                if name.startswith("assets/")
            }
            if archive_asset_paths != expected_asset_paths:
                extra = sorted(archive_asset_paths - expected_asset_paths)
                missing = sorted(expected_asset_paths - archive_asset_paths)
                raise BackupError(
                    "资产清单不一致"
                    + (f"，额外：{extra[:3]}" if extra else "")
                    + (f"，缺少：{missing[:3]}" if missing else "")
                )

        _sanitize_portable_database(staging_database)
        _inject_local_settings(
            staging_database,
            preserved_settings=preserved_settings,
            database_instance_id=database_instance_id,
        )
        staged_validation = _validate_database(staging_database, expected_revision=expected_revision)
        staged_hash = _sha256_file(staging_database)
        staged_assets = [
            {
                "path": entry["path"],
                "size": int(entry["size"]),
                "sha256": str(entry["sha256"]),
            }
            for entry in manifest.get("assets", [])
        ]
        marker = {
            "format_version": PENDING_FORMAT_VERSION,
            "restore_id": restore_id,
            "staged_at": _utc_now(),
            "backup_created_at": str(manifest.get("created_at", "")),
            "source_app_version": str(manifest.get("app_version", "")),
            "alembic_revision": expected_revision,
            "target_database_path": str(database_path.resolve(strict=False)),
            "target_database_instance_id": database_instance_id,
            "staging_dir": str(staging_dir.resolve(strict=False)),
            "database_path": str(staging_database.resolve(strict=False)),
            "database_sha256": staged_hash,
            "counts": staged_validation["counts"],
            "assets": staged_assets,
            "asset_count": len(staged_assets),
            "preserved_sensitive_settings": sorted(
                key for key in preserved_settings if _is_sensitive_setting_key(key)
            ),
        }
        _write_json_atomic(staging_dir / MANIFEST_ARCHIVE_PATH, manifest)
        _write_json_atomic(marker_path, marker)
        logger.warning(
            "Restore package staged; restart required restore_id=%s counts=%s",
            restore_id,
            staged_validation["counts"],
        )
        return _pending_public_payload(marker)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        marker_path.unlink(missing_ok=True)
        raise


def cancel_pending_restore(*, data_dir: Path) -> bool:
    marker = _load_pending_marker(data_dir)
    if marker is None:
        return False
    staging_dir = Path(str(marker.get("staging_dir", ""))).expanduser()
    expected_root = data_dir / STAGING_DIRECTORY_NAME
    if _normalized_path(staging_dir).startswith(_normalized_path(expected_root) + os.sep):
        shutil.rmtree(staging_dir, ignore_errors=True)
    _pending_marker_path(data_dir).unlink(missing_ok=True)
    logger.info("Pending restore cancelled: %s", marker.get("restore_id"))
    return True


def _validate_pending_paths(
    *,
    marker: dict[str, Any],
    data_dir: Path,
    database_path: Path,
) -> tuple[Path, Path]:
    target_path = Path(str(marker.get("target_database_path", ""))).expanduser()
    if _normalized_path(target_path) != _normalized_path(database_path):
        raise BackupError("待恢复任务的目标数据库路径与当前登记不一致")
    staging_dir = Path(str(marker.get("staging_dir", ""))).expanduser()
    allowed_staging_root = (data_dir / STAGING_DIRECTORY_NAME).resolve(strict=False)
    resolved_staging = staging_dir.resolve(strict=False)
    try:
        resolved_staging.relative_to(allowed_staging_root)
    except ValueError as error:
        raise BackupError("待恢复目录不在受管理的数据目录中") from error
    staged_database = Path(str(marker.get("database_path", ""))).expanduser().resolve(strict=False)
    try:
        staged_database.relative_to(resolved_staging)
    except ValueError as error:
        raise BackupError("待恢复数据库路径无效") from error
    return resolved_staging, staged_database


def _copy_asset_tree(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        destination.mkdir(parents=True, exist_ok=True)


def _restore_assets_from_safety(
    *,
    safety_dir: Path,
    data_dir: Path,
    old_asset_dirs: dict[str, Path],
) -> None:
    for directory_name in ASSET_DIRECTORIES:
        destination = data_dir / directory_name
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        old_dir = old_asset_dirs.get(directory_name)
        if old_dir and old_dir.exists():
            os.replace(old_dir, destination)
            continue
        source = safety_dir / "assets" / directory_name
        _copy_asset_tree(source, destination)


def _rollback_applied_restore(application: RestoreApplication) -> None:
    safety_database = application.safety_dir / DATABASE_ARCHIVE_PATH
    if safety_database.exists():
        _copy_static_database(safety_database, application.database_path)
    _restore_assets_from_safety(
        safety_dir=application.safety_dir,
        data_dir=application.database_path.parent,
        old_asset_dirs=application.old_asset_dirs,
    )


def apply_pending_restore(
    *,
    data_dir: Path,
    backups_dir: Path,
    database_path: Path,
    registry: dict[str, Any],
) -> RestoreApplication | None:
    """Apply a validated restore before SQLAlchemy opens the managed database."""
    marker = _load_pending_marker(data_dir)
    if marker is None:
        return None

    registered_id = str(registry.get("database_instance_id", "")).strip()
    target_id = str(marker.get("target_database_instance_id", "")).strip()
    if not registered_id or target_id != registered_id:
        raise BackupError("待恢复任务与当前数据库身份不匹配")

    staging_dir, staged_database = _validate_pending_paths(
        marker=marker,
        data_dir=data_dir,
        database_path=database_path,
    )
    if not staged_database.exists():
        raise BackupError("待恢复数据库文件不存在")
    if _sha256_file(staged_database) != str(marker.get("database_sha256", "")):
        raise BackupError("待恢复数据库哈希校验失败")
    expected_revision = str(marker.get("alembic_revision", ""))
    validation = _validate_database(staged_database, expected_revision=expected_revision)
    staged_settings = _read_settings(staged_database)
    if staged_settings.get(INSTANCE_SETTING_KEY) != registered_id:
        raise BackupError("待恢复数据库没有正确绑定当前存储身份")

    for asset in marker.get("assets", []):
        if not isinstance(asset, dict):
            raise BackupError("待恢复资产清单无效")
        relative = _safe_zip_name(str(asset.get("path", "")))
        source = staging_dir.joinpath(*PurePosixPath(relative).parts)
        if not source.exists() or not source.is_file():
            raise BackupError(f"待恢复资产不存在：{relative}")
        if source.stat().st_size != int(asset.get("size", -1)):
            raise BackupError(f"待恢复资产大小不匹配：{relative}")
        if _sha256_file(source) != str(asset.get("sha256", "")):
            raise BackupError(f"待恢复资产哈希不匹配：{relative}")

    restore_id = str(marker.get("restore_id", "")) or uuid4().hex
    backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safety_dir = backups_dir / f"pre_restore_{timestamp}_{restore_id[:8]}"
    safety_dir.mkdir(parents=True, exist_ok=False)
    old_asset_dirs: dict[str, Path] = {}
    application = RestoreApplication(
        restore_id=restore_id,
        marker_path=_pending_marker_path(data_dir),
        staging_dir=staging_dir,
        safety_dir=safety_dir,
        database_path=database_path,
        old_asset_dirs=old_asset_dirs,
        summary={"counts": validation["counts"], "backup_created_at": marker.get("backup_created_at")},
    )

    try:
        _copy_sqlite_database(database_path, safety_dir / DATABASE_ARCHIVE_PATH)
        for directory_name in ASSET_DIRECTORIES:
            _copy_asset_tree(data_dir / directory_name, safety_dir / "assets" / directory_name)
        _write_json_atomic(
            safety_dir / "safety.json",
            {
                "format": "ai-tavern-pre-restore-safety",
                "created_at": _utc_now(),
                "restore_id": restore_id,
                "database_path": str(database_path.resolve(strict=False)),
            },
        )

        _copy_static_database(staged_database, database_path)
        for directory_name in ASSET_DIRECTORIES:
            source = staging_dir / "assets" / directory_name
            destination = data_dir / directory_name
            incoming = data_dir / f".{directory_name}.restore-new.{restore_id}"
            old = data_dir / f".{directory_name}.restore-old.{restore_id}"
            shutil.rmtree(incoming, ignore_errors=True)
            shutil.rmtree(old, ignore_errors=True)
            _copy_asset_tree(source, incoming)
            if destination.exists():
                os.replace(destination, old)
                old_asset_dirs[directory_name] = old
            os.replace(incoming, destination)

        logger.warning(
            "Pending restore applied before startup restore_id=%s safety=%s counts=%s",
            restore_id,
            safety_dir,
            validation["counts"],
        )
        return application
    except Exception:
        try:
            _rollback_applied_restore(application)
        except Exception as rollback_error:
            logger.critical("Restore application and rollback both failed: %s", rollback_error)
        raise


def rollback_pending_restore(application: RestoreApplication) -> None:
    if application.finalized:
        return
    _rollback_applied_restore(application)
    application.marker_path.unlink(missing_ok=True)
    shutil.rmtree(application.staging_dir, ignore_errors=True)
    for old_dir in application.old_asset_dirs.values():
        shutil.rmtree(old_dir, ignore_errors=True)
    application.finalized = True
    logger.error(
        "Pending restore rolled back after startup failure restore_id=%s safety=%s",
        application.restore_id,
        application.safety_dir,
    )


def commit_pending_restore(application: RestoreApplication) -> None:
    if application.finalized:
        return
    application.marker_path.unlink(missing_ok=True)
    shutil.rmtree(application.staging_dir, ignore_errors=True)
    for old_dir in application.old_asset_dirs.values():
        shutil.rmtree(old_dir, ignore_errors=True)
    application.finalized = True
    logger.warning(
        "Restore completed restore_id=%s pre_restore_safety=%s",
        application.restore_id,
        application.safety_dir,
    )
