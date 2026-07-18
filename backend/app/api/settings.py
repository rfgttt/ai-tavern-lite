from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.config import settings as runtime_settings
from ..core.security import UnsafeOutboundURLError, validate_outbound_url
from ..db.session import get_db
from ..schemas import ConnectionTestResult, SettingsResponse, SettingsUpdate
from ..services.llm.provider import get_provider
from ..services.settings_service import SettingsService

router = APIRouter(tags=["settings"])


def _validate_base_url(base_url: str) -> None:
    if not str(base_url or "").strip():
        return
    try:
        validate_outbound_url(
            base_url,
            allow_private_hosts=runtime_settings.allow_private_llm_hosts,
            allowed_hosts=runtime_settings.llm_allowed_host_items,
        )
    except UnsafeOutboundURLError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _settings_response(db: Session) -> SettingsResponse:
    app_settings = SettingsService.get_masked_settings(db)
    app_settings.update(
        settings_writable=runtime_settings.allow_settings_write,
        diagnostics_enabled=runtime_settings.enable_diagnostics,
        selftest_enabled=runtime_settings.enable_selftest,
    )
    return SettingsResponse(**app_settings)


@router.get("/settings", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    """Get current settings (API key masked)."""
    return _settings_response(db)


@router.put("/settings", response_model=SettingsResponse)
def update_settings(update: SettingsUpdate, db: Session = Depends(get_db)):
    """Update settings when runtime writes are explicitly enabled."""
    if not runtime_settings.allow_settings_write:
        raise HTTPException(
            status_code=403,
            detail="生产环境已锁定模型设置，请通过服务器环境变量修改",
        )

    update_dict = update.model_dump(exclude_unset=True)
    current = SettingsService.get_all_settings(db)
    candidate = {**current, **update_dict}
    if candidate["max_tokens"] >= candidate["context_window"]:
        raise HTTPException(status_code=422, detail="max_tokens 必须小于 context_window")
    _validate_base_url(candidate.get("base_url", ""))

    SettingsService.update_settings(db, update_dict)
    return _settings_response(db)


@router.post("/settings/test-connection", response_model=ConnectionTestResult)
async def test_connection(update: SettingsUpdate | None = None, db: Session = Depends(get_db)):
    """Test saved settings; temporary client-supplied endpoints can be disabled in production."""
    if update is not None and not runtime_settings.allow_settings_write:
        raise HTTPException(
            status_code=403,
            detail="生产环境不允许提交临时模型地址，请测试服务器环境变量中的配置",
        )

    app_settings = SettingsService.get_all_settings(db)
    if update is not None:
        candidate = update.model_dump(exclude_unset=True)
        candidate.pop("clear_api_key", None)
        if not candidate.get("api_key"):
            candidate.pop("api_key", None)
        app_settings = {**app_settings, **candidate}

    mock_mode = app_settings.get("mock_llm", True)
    if mock_mode:
        return ConnectionTestResult(success=True, message="Mock 模式正常运行，无需 API Key")

    base_url = app_settings.get("base_url", "")
    api_key = app_settings.get("api_key", "")
    model = app_settings.get("model", "")

    if not base_url or not api_key or not model:
        return ConnectionTestResult(
            success=False,
            message="请先填写 Base URL、API Key 和 Model ID",
        )

    _validate_base_url(base_url)
    provider = get_provider(
        mock_mode=False,
        base_url=base_url,
        api_key=api_key,
        model=model,
    )

    success, message = await provider.test_connection()
    return ConnectionTestResult(success=success, message=message, model=model)
