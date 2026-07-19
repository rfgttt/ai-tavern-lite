from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from ..core.config import settings
from ..core.logging import logger
from ..db.migrations import get_head_revision
from ..db.models import AppSetting
from ..db.session import engine, get_db
from ..schemas import BackupRestoreResponse, BackupStatusResponse
from ..services.backup.service import (
    BackupError,
    INSTANCE_SETTING_KEY,
    build_backup_archive,
    cancel_pending_restore,
    get_backup_status,
    stage_restore_archive,
)


router = APIRouter(prefix="/backups", tags=["backups"])


def _database_path() -> Path:
    url = make_url(engine.url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise BackupError("完整备份与恢复 V1 目前仅支持 SQLite")
    path = Path(url.database).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve(strict=False)
    return path


def _preserved_sensitive_settings(db: Session) -> tuple[dict[str, str], str]:
    rows = db.query(AppSetting).all()
    values = {str(row.key): str(row.value or "") for row in rows}
    instance_id = values.get(INSTANCE_SETTING_KEY, "").strip()
    preserved = {
        key: value
        for key, value in values.items()
        if key in {"api_key", "custom_headers"}
        or any(marker in key.lower() for marker in ("secret", "password", "token", "authorization"))
    }
    return preserved, instance_id


def _cleanup_directory(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


@router.get("/status", response_model=BackupStatusResponse)
def backup_status():
    try:
        return get_backup_status(
            data_dir=settings.data_dir,
            database_path=_database_path(),
        )
    except BackupError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/export")
def export_backup():
    try:
        result = build_backup_archive(
            database_path=_database_path(),
            avatars_dir=settings.avatars_dir,
            characters_dir=settings.characters_dir,
            exports_dir=settings.exports_dir,
            max_uncompressed_bytes=settings.max_backup_uncompressed_mb * 1024 * 1024,
        )
    except BackupError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        logger.exception("Portable backup creation failed")
        raise HTTPException(status_code=500, detail="创建完整备份失败") from error

    return FileResponse(
        result.archive_path,
        media_type="application/zip",
        filename=result.filename,
        background=BackgroundTask(_cleanup_directory, result.cleanup_root),
        headers={
            "X-AI-Tavern-Backup-Format": str(result.manifest["format_version"]),
            "Cache-Control": "no-store",
        },
    )


@router.post("/restore", response_model=BackupRestoreResponse)
async def prepare_restore(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    max_size = settings.max_backup_size_mb * 1024 * 1024
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upload_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="restore-upload-",
            suffix=".zip",
            dir=str(settings.data_dir),
            delete=False,
        ) as handle:
            upload_path = Path(handle.name)
            total = 0
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size:
                    raise BackupError(
                        f"备份包超过 {settings.max_backup_size_mb}MB 上传限制"
                    )
                handle.write(chunk)
            handle.flush()

        if not upload_path.exists() or upload_path.stat().st_size == 0:
            raise BackupError("上传的备份包为空")

        preserved, instance_id = _preserved_sensitive_settings(db)
        pending = stage_restore_archive(
            archive_path=upload_path,
            data_dir=settings.data_dir,
            database_path=_database_path(),
            expected_revision=get_head_revision(),
            database_instance_id=instance_id,
            preserved_settings=preserved,
            max_entries=settings.max_backup_entries,
            max_uncompressed_bytes=settings.max_backup_uncompressed_mb * 1024 * 1024,
        )
        return BackupRestoreResponse(
            success=True,
            message="恢复包已验证并暂存。请停止服务后重新启动，恢复才会生效。",
            **pending,
        )
    except BackupError as error:
        status_code = 409 if "已有待执行" in str(error) else 400
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    except Exception as error:
        logger.exception("Restore package staging failed")
        raise HTTPException(status_code=500, detail="准备恢复失败，当前数据库未被修改") from error
    finally:
        await file.close()
        if upload_path is not None:
            upload_path.unlink(missing_ok=True)


@router.delete("/restore/pending")
def cancel_restore():
    try:
        cancelled = cancel_pending_restore(data_dir=settings.data_dir)
    except BackupError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return {
        "success": True,
        "cancelled": cancelled,
        "message": "待恢复任务已取消" if cancelled else "当前没有待恢复任务",
    }
