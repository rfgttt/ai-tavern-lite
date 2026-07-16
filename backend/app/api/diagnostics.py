from __future__ import annotations

from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.models import Character, ChatSession, Memory, Message, SessionState, TurnSnapshot
from ..db.session import get_db
from ..services.diagnostics.service import diagnostic_service
from ..services.settings_service import SettingsService

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


def _database_summary(db: Session) -> dict:
    return {
        "characters": db.query(Character).count(),
        "sessions": db.query(ChatSession).count(),
        "messages": db.query(Message).count(),
        "memories": db.query(Memory).count(),
        "session_states": db.query(SessionState).count(),
        "turn_snapshots": db.query(TurnSnapshot).count(),
    }


def _health_payload(db: Session) -> dict:
    app_settings = SettingsService.get_all_settings(db)
    database_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database_ok = False

    state_engine_ok = True
    try:
        from ..services.runtime.state_engine import apply_patch  # noqa: F401
    except Exception:
        state_engine_ok = False

    mock_mode = bool(app_settings.get("mock_llm", True))
    provider_configured = mock_mode or all(
        bool(app_settings.get(key)) for key in ("base_url", "api_key", "model")
    )
    frontend_build = (
        settings.frontend_dist_dir.exists()
        and (settings.frontend_dist_dir / "index.html").exists()
    )
    log_writable = diagnostic_service.log_writable()
    components = {
        "backend": True,
        "database": database_ok,
        "frontend_build": frontend_build,
        "provider_configured": provider_configured,
        "state_engine": state_engine_ok,
        "log_writable": log_writable,
    }
    required = (database_ok, state_engine_ok, log_writable)
    return {
        "status": "ok" if all(required) else "degraded",
        "version": "2.2.0-preview.1",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "mock_mode": mock_mode,
        "provider": app_settings.get("provider_name", ""),
        "model": app_settings.get("model", ""),
        "components": components,
    }


@router.get("/health")
def diagnostics_health(db: Session = Depends(get_db)):
    return _health_payload(db)


@router.get("/latest")
def diagnostics_latest():
    return diagnostic_service.get_latest_request()


@router.post("/export")
def export_diagnostics(db: Session = Depends(get_db)):
    try:
        app_settings = SettingsService.get_all_settings(db)
        archive = diagnostic_service.build_export_bytes(
            health=_health_payload(db),
            system=diagnostic_service.system_info("2.2.0-preview.1"),
            settings_payload=app_settings,
            database_summary=_database_summary(db),
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail="生成诊断包失败") from error

    filename = f"ai-tavern-diagnostics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        BytesIO(archive),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/logs")
def clear_diagnostics_logs():
    diagnostic_service.clear_logs()
    return {"success": True, "message": "诊断日志已清空"}
