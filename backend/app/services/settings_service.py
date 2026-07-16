import json
import re
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from ..core.config import settings as default_settings
from ..core.logging import logger
from ..db.models import AppSetting


_HEADER_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_BLOCKED_HEADERS = {
    "host", "content-length", "transfer-encoding", "connection",
    "proxy-authorization", "proxy-authenticate", "upgrade", "te", "trailer",
}


def _sanitize_custom_headers(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: Dict[str, str] = {}
    for raw_name, raw_value in list(value.items())[:20]:
        name = str(raw_name).strip()
        header_value = str(raw_value)
        if (
            not _HEADER_TOKEN.fullmatch(name)
            or name.lower() in _BLOCKED_HEADERS
            or len(header_value) > 4096
            or "\r" in header_value
            or "\n" in header_value
        ):
            logger.warning("Ignored unsafe custom header: %s", name[:80])
            continue
        result[name] = header_value
    return result


class SettingsService:
    """Service for managing application settings stored in database."""

    DEFAULTS = {
        "provider_name": "OpenAI Compatible",
        "base_url": "",
        "api_key": "",
        "model": "",
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 1024,
        "context_window": 8192,
        "username": "用户",
        "mock_llm": True,
        "auto_memory_extraction": False,
        "custom_headers": {},
    }

    ENV_FIELD_MAP = {
        "base_url": "base_url",
        "api_key": "api_key",
        "model": "model",
        "provider_name": "provider_name",
        "mock_llm": "mock_llm",
        "username": "default_username",
        "temperature": "default_temperature",
        "top_p": "default_top_p",
        "max_tokens": "default_max_tokens",
        "context_window": "default_context_window",
        "auto_memory_extraction": "auto_memory_extraction",
    }

    @staticmethod
    def _get_setting(db: Session, key: str) -> Optional[str]:
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        return setting.value if setting else None

    @staticmethod
    def _set_setting(db: Session, key: str, value: str):
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if setting:
            setting.value = value
        else:
            db.add(AppSetting(key=key, value=value))
        db.commit()

    @classmethod
    def get_all_settings(cls, db: Session) -> Dict[str, Any]:
        """Get all settings, with explicitly configured env values overriding DB."""
        result: Dict[str, Any] = {}

        for key, default_val in cls.DEFAULTS.items():
            db_val = cls._get_setting(db, key)
            if db_val is None:
                result[key] = default_val
            elif isinstance(default_val, bool):
                result[key] = db_val.lower() == "true"
            elif isinstance(default_val, (int, float)):
                try:
                    result[key] = type(default_val)(db_val)
                except (ValueError, TypeError):
                    result[key] = default_val
            elif isinstance(default_val, dict):
                try:
                    result[key] = json.loads(db_val)
                except (json.JSONDecodeError, TypeError):
                    result[key] = {}
            else:
                result[key] = db_val

        explicitly_configured = default_settings.model_fields_set
        for result_key, settings_field in cls.ENV_FIELD_MAP.items():
            if settings_field in explicitly_configured:
                result[result_key] = getattr(default_settings, settings_field)

        result["custom_headers"] = _sanitize_custom_headers(result.get("custom_headers"))
        result["context_window"] = min(max(int(result.get("context_window", 8192)), 128), 1_000_000)
        result["max_tokens"] = min(max(int(result.get("max_tokens", 1024)), 1), 32_768)
        if result["max_tokens"] >= result["context_window"]:
            result["max_tokens"] = max(1, result["context_window"] - 1)

        return result

    @classmethod
    def update_settings(cls, db: Session, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update settings. Empty API key means keep existing value."""
        if updates.get("clear_api_key"):
            cls._set_setting(db, "api_key", "")

        for key, value in updates.items():
            if key == "clear_api_key" or key not in cls.DEFAULTS:
                continue
            if key == "api_key" and (value is None or value == ""):
                continue

            if isinstance(value, bool):
                str_val = "true" if value else "false"
            elif isinstance(value, (int, float)):
                str_val = str(value)
            elif isinstance(value, dict):
                str_val = json.dumps(value, ensure_ascii=False)
            else:
                str_val = str(value) if value is not None else ""

            cls._set_setting(db, key, str_val)

        logger.info("Settings updated")
        return cls.get_all_settings(db)

    @classmethod
    def get_masked_settings(cls, db: Session) -> Dict[str, Any]:
        """Get settings with API key masked (for frontend)."""
        settings = cls.get_all_settings(db)
        api_key = settings.get("api_key", "")

        if api_key and len(api_key) > 8:
            masked = api_key[:4] + "****" + api_key[-4:]
        elif api_key:
            masked = "****"
        else:
            masked = ""

        result = {k: v for k, v in settings.items() if k != "api_key"}
        result["api_key_configured"] = bool(api_key)
        result["api_key_masked"] = masked
        return result
