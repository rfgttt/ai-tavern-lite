from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.models import Character, ChatSession, Memory, Message, SessionState, TurnSnapshot
from ..db.session import get_db
from ..services.diagnostics.service import diagnostic_service
from ..services.selftest.service import selftest_service
from ..services.settings_service import SettingsService

router = APIRouter(prefix="/self-test", tags=["self-test"])


def _database_summary(db: Session) -> dict[str, int]:
    return {
        "characters": db.query(Character).count(),
        "sessions": db.query(ChatSession).count(),
        "messages": db.query(Message).count(),
        "memories": db.query(Memory).count(),
        "session_states": db.query(SessionState).count(),
        "turn_snapshots": db.query(TurnSnapshot).count(),
    }


def _health(db: Session) -> dict[str, Any]:
    database_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database_ok = False
    return {
        "status": "ok" if database_ok else "degraded",
        "version": "2.2.0-preview.1-selftest",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "database": database_ok,
        "frontend_build": settings.frontend_dist_dir.exists() and (settings.frontend_dist_dir / "index.html").exists(),
        "log_writable": diagnostic_service.log_writable(),
    }


@router.post("/runs")
def create_selftest_run():
    return selftest_service.create_run()


@router.get("/runs/{run_id}")
def get_selftest_run(run_id: str):
    try:
        payload = selftest_service.get_run(run_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if payload is None:
        raise HTTPException(status_code=404, detail="自检运行不存在")
    return payload


@router.post("/runs/{run_id}/backend")
def submit_backend_result(run_id: str, report: dict[str, Any]):
    return _submit(run_id, "backend", report)


@router.post("/runs/{run_id}/frontend")
def submit_frontend_result(run_id: str, report: dict[str, Any]):
    return _submit(run_id, "frontend", report)


@router.post("/runs/{run_id}/context")
def submit_context(run_id: str, report: dict[str, Any]):
    return _submit(run_id, "context", report)


def _submit(run_id: str, component: str, report: dict[str, Any]):
    try:
        return selftest_service.update_component(run_id, component, report)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="自检运行不存在") from error


@router.post("/runs/{run_id}/export")
def export_selftest_run(run_id: str, db: Session = Depends(get_db)):
    try:
        app_settings = SettingsService.get_all_settings(db)
        diagnostics_bundle = diagnostic_service.build_export_bytes(
            health=_health(db),
            system=diagnostic_service.system_info("2.2.0-preview.1-selftest"),
            settings_payload=app_settings,
            database_summary=_database_summary(db),
        )
        archive = selftest_service.build_export_bytes(run_id, diagnostics_bundle)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="自检运行不存在") from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="生成自检报告失败") from error

    filename = f"ai-tavern-self-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        BytesIO(archive),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
