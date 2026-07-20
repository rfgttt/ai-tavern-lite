import hmac
import json
import re
from typing import Any, Dict, Optional

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from ..core.config import settings as default_settings
from ..core.logging import logger
from ..db.models import AppSetting
from .secrets import ApiKeyStorageError, create_api_key_store


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
    """Manage non-secret settings in SQLite and API keys in secure storage."""

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
        "auto_state_update_recovery": True,
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
        "auto_state_update_recovery": "auto_state_update_recovery",
    }

    API_KEY_STORE = create_api_key_store(default_settings.api_key_secret_path)

    @staticmethod
    def _get_setting(db: Session, key: str) -> Optional[str]:
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        return setting.value if setting else None

    @staticmethod
    def _set_setting(db: Session, key: str, value: str, *, commit: bool = True) -> None:
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if setting:
            setting.value = value
        else:
            db.add(AppSetting(key=key, value=value))
        if commit:
            db.commit()

    @classmethod
    def _delete_setting(cls, db: Session, key: str, *, scrub_sqlite: bool = False) -> bool:
        bind = db.get_bind()
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if setting is None:
            return False

        if scrub_sqlite and bind is not None and bind.dialect.name == "sqlite":
            db.execute(text("PRAGMA secure_delete=ON"))

        db.delete(setting)
        db.commit()

        if scrub_sqlite and bind is not None and bind.dialect.name == "sqlite":
            try:
                with bind.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                    connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
                    connection.exec_driver_sql("VACUUM")
            except Exception as error:
                raise ApiKeyStorageError(
                    "API Key 已移出数据库，但 SQLite 安全清理失败；请停止服务后重试"
                ) from error
        return True

    @classmethod
    def api_key_is_environment_managed(cls) -> bool:
        return "api_key" in default_settings.model_fields_set

    @classmethod
    def migrate_plaintext_api_key(cls, db: Session) -> bool:
        """Move a legacy SQLite API key into DPAPI before future DB backups."""
        if not cls.API_KEY_STORE.available:
            return False

        bind = db.get_bind()
        if bind is None or not inspect(bind).has_table(AppSetting.__tablename__):
            return False

        setting = db.query(AppSetting).filter(AppSetting.key == "api_key").first()
        if setting is None:
            return False

        legacy_value = str(setting.value or "")
        if not legacy_value:
            cls._delete_setting(db, "api_key", scrub_sqlite=True)
            return True

        existing_value = cls.API_KEY_STORE.read()
        if existing_value and not hmac.compare_digest(existing_value, legacy_value):
            raise ApiKeyStorageError(
                "数据库与 Windows DPAPI 中存在不同的 API Key，已拒绝自动覆盖；"
                "请先备份并在设置中明确清除或替换"
            )

        if not existing_value:
            cls.API_KEY_STORE.write(legacy_value)
            verified_value = cls.API_KEY_STORE.read()
            if not hmac.compare_digest(verified_value, legacy_value):
                raise ApiKeyStorageError("API Key 写入 Windows DPAPI 后校验失败")

        cls._delete_setting(db, "api_key", scrub_sqlite=True)
        logger.info("Legacy plaintext API key migrated to Windows DPAPI")
        return True

    @classmethod
    def _read_api_key(cls, db: Session) -> str:
        if cls.api_key_is_environment_managed():
            return default_settings.api_key

        if cls.API_KEY_STORE.available:
            return cls.API_KEY_STORE.read()

        return cls._get_setting(db, "api_key") or ""

    @classmethod
    def _get_non_secret_settings(cls, db: Session) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        for key, default_val in cls.DEFAULTS.items():
            if key == "api_key":
                continue
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
            if result_key == "api_key":
                continue
            if settings_field in explicitly_configured:
                result[result_key] = getattr(default_settings, settings_field)

        result["custom_headers"] = _sanitize_custom_headers(result.get("custom_headers"))
        result["context_window"] = min(max(int(result.get("context_window", 8192)), 128), 1_000_000)
        result["max_tokens"] = min(max(int(result.get("max_tokens", 1024)), 1), 32_768)
        if result["max_tokens"] >= result["context_window"]:
            result["max_tokens"] = max(1, result["context_window"] - 1)
        return result

    @classmethod
    def get_non_secret_settings(cls, db: Session) -> Dict[str, Any]:
        """Get settings that do not require reading the API key."""
        return cls._get_non_secret_settings(db)

    @classmethod
    def get_all_settings(cls, db: Session) -> Dict[str, Any]:
        """Get runtime settings, including the decrypted API key for backend use."""
        result = cls._get_non_secret_settings(db)
        result["api_key"] = cls._read_api_key(db)
        return result

    @classmethod
    def update_settings(cls, db: Session, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Atomically update database settings and roll back secure-key changes on failure."""
        requested_api_key = updates.get("api_key")
        wants_api_key_change = bool(updates.get("clear_api_key")) or bool(requested_api_key)
        if wants_api_key_change and cls.api_key_is_environment_managed():
            raise ApiKeyStorageError("API Key 由服务器环境变量管理，不能在网页中替换或清除")

        old_secret = None
        old_secret_readable = True
        secret_changed = False
        if wants_api_key_change and cls.API_KEY_STORE.available:
            try:
                old_secret = cls.API_KEY_STORE.read()
            except ApiKeyStorageError:
                if updates.get("clear_api_key"):
                    old_secret_readable = False
                else:
                    raise

        try:
            for key, value in updates.items():
                if key in {"clear_api_key", "api_key"} or key not in cls.DEFAULTS:
                    continue
                if isinstance(value, bool):
                    str_val = "true" if value else "false"
                elif isinstance(value, (int, float)):
                    str_val = str(value)
                elif isinstance(value, dict):
                    str_val = json.dumps(_sanitize_custom_headers(value), ensure_ascii=False)
                else:
                    str_val = str(value) if value is not None else ""
                cls._set_setting(db, key, str_val, commit=False)

            if updates.get("clear_api_key"):
                if cls.API_KEY_STORE.available:
                    cls.API_KEY_STORE.clear()
                    secret_changed = True
                    setting = db.query(AppSetting).filter(AppSetting.key == "api_key").first()
                    if setting is not None:
                        db.delete(setting)
                else:
                    cls._set_setting(db, "api_key", "", commit=False)
            elif requested_api_key:
                normalized = str(requested_api_key)
                if cls.API_KEY_STORE.available:
                    cls.API_KEY_STORE.write(normalized)
                    secret_changed = True
                    verified = cls.API_KEY_STORE.read()
                    if not hmac.compare_digest(verified, normalized):
                        raise ApiKeyStorageError("API Key 写入 Windows DPAPI 后校验失败")
                    setting = db.query(AppSetting).filter(AppSetting.key == "api_key").first()
                    if setting is not None:
                        db.delete(setting)
                else:
                    cls._set_setting(db, "api_key", normalized, commit=False)

            db.commit()
        except Exception:
            db.rollback()
            if secret_changed and cls.API_KEY_STORE.available and old_secret_readable:
                try:
                    if old_secret:
                        cls.API_KEY_STORE.write(old_secret)
                    else:
                        cls.API_KEY_STORE.clear()
                except Exception as restore_error:
                    logger.error("Failed to restore API key after settings rollback: %s", restore_error)
            raise

        logger.info("Settings updated")
        return cls.get_all_settings(db)

    @classmethod
    def get_masked_settings(cls, db: Session) -> Dict[str, Any]:
        """Get settings without returning the full API key to the frontend."""
        result = cls._get_non_secret_settings(db)
        error_message = ""

        if cls.api_key_is_environment_managed():
            api_key = default_settings.api_key
            configured = bool(api_key)
            storage = "environment"
        elif cls.API_KEY_STORE.available:
            storage = cls.API_KEY_STORE.backend_name
            try:
                configured = cls.API_KEY_STORE.is_configured()
                api_key = cls.API_KEY_STORE.read() if configured else ""
            except ApiKeyStorageError as error:
                configured = cls.API_KEY_STORE.is_configured()
                api_key = ""
                error_message = str(error)
        else:
            storage = "database_legacy"
            api_key = cls._get_setting(db, "api_key") or ""
            configured = bool(api_key)

        if api_key and len(api_key) > 4:
            masked = "••••••••" + api_key[-4:]
        elif api_key:
            masked = "••••••••"
        else:
            masked = ""

        result["api_key_configured"] = configured
        result["api_key_masked"] = masked
        result["api_key_storage"] = storage
        result["api_key_error"] = error_message
        return result
