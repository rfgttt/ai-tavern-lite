from __future__ import annotations

import os
from pathlib import Path

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _backend_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _default_user_data_dir() -> Path:
    """Return a storage root that stays stable when the source tree moves."""
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if local_app_data:
            return Path(local_app_data) / "AI-Tavern-Lite" / "data"
        return Path.home() / "AppData" / "Local" / "AI-Tavern-Lite" / "data"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "AI-Tavern-Lite" / "data"
    return Path.home() / ".local" / "share" / "AI-Tavern-Lite" / "data"


def _default_database_url() -> str:
    return f"sqlite:///{(_default_user_data_dir() / 'ai_tavern.db').as_posix()}"


def _csv_items(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in str(raw or "").split(",") if item.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AI_TAVERN_",
        case_sensitive=False,
        extra="ignore",
    )

    base_dir: Path = _backend_dir()
    legacy_data_dir: Path = _backend_dir() / "data"
    data_dir: Path = _default_user_data_dir()
    characters_dir: Path = _default_user_data_dir() / "characters"
    avatars_dir: Path = _default_user_data_dir() / "avatars"
    exports_dir: Path = _default_user_data_dir() / "exports"
    backups_dir: Path = _default_user_data_dir() / "backups"
    logs_dir: Path = _default_user_data_dir() / "logs"
    diagnostics_dir: Path = _default_user_data_dir() / "diagnostics"
    secrets_dir: Path = _default_user_data_dir().parent / "secrets"
    api_key_secret_path: Path = _default_user_data_dir().parent / "secrets" / "api-key.dpapi"
    storage_registry_path: Path = _default_user_data_dir().parent / "storage.json"

    environment: str = "development"
    database_url: str = _default_database_url()
    storage_guard_enabled: bool = True
    max_upload_size_mb: int = 20
    max_backup_size_mb: int = 256
    max_backup_uncompressed_mb: int = 1024
    max_backup_entries: int = 10_000
    max_json_body_bytes: int = 2 * 1024 * 1024
    max_request_body_bytes: int = 24 * 1024 * 1024

    mock_llm: bool = False
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    provider_name: str = "OpenAI Compatible"
    allow_private_llm_hosts: bool = False
    llm_allowed_hosts: str = ""
    allow_settings_write: bool = True

    default_temperature: float = 0.7
    default_top_p: float = 0.9
    default_max_tokens: int = 1024
    default_context_window: int = 8192

    max_memory_entries: int = 12
    auto_memory_extraction: bool = False
    auto_state_update_recovery: bool = True

    default_username: str = "用户"

    host: str = "127.0.0.1"
    port: int = 8000
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    auth_enabled: bool = False
    auth_username: str = "admin"
    auth_password: SecretStr = SecretStr("")
    auth_exempt_paths_csv: str = "/api/health"

    rate_limit_enabled: bool = False
    rate_limit_requests: int = 180
    rate_limit_window_seconds: int = 60
    ai_rate_limit_requests: int = 12
    ai_rate_limit_window_seconds: int = 60
    max_concurrent_generations: int = 2

    enable_diagnostics: bool = True
    enable_selftest: bool = True
    create_demo_data: bool = False

    frontend_dist_dir: Path = base_dir.parent / "frontend" / "dist"

    @model_validator(mode="after")
    def _derive_storage_paths(self) -> "Settings":
        """Keep all managed storage paths under the selected data directory."""
        explicit = self.model_fields_set
        self.data_dir = Path(self.data_dir).expanduser()
        self.legacy_data_dir = Path(self.legacy_data_dir).expanduser()

        derived_paths = {
            "characters_dir": self.data_dir / "characters",
            "avatars_dir": self.data_dir / "avatars",
            "exports_dir": self.data_dir / "exports",
            "backups_dir": self.data_dir / "backups",
            "logs_dir": self.data_dir / "logs",
            "diagnostics_dir": self.data_dir / "diagnostics",
            "secrets_dir": self.data_dir.parent / "secrets",
            "api_key_secret_path": self.data_dir.parent / "secrets" / "api-key.dpapi",
            "storage_registry_path": self.data_dir.parent / "storage.json",
        }
        for field_name, path in derived_paths.items():
            if field_name not in explicit:
                setattr(self, field_name, path)
            else:
                setattr(self, field_name, Path(getattr(self, field_name)).expanduser())

        if "api_key_secret_path" not in explicit:
            self.api_key_secret_path = self.secrets_dir / "api-key.dpapi"

        if "database_url" not in explicit:
            self.database_url = f"sqlite:///{(self.data_dir / 'ai_tavern.db').as_posix()}"
        return self

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}

    @property
    def uses_managed_storage(self) -> bool:
        """Only the canonical database under data_dir is identity-managed."""
        prefix = "sqlite:///"
        if not self.storage_guard_enabled or not self.database_url.startswith(prefix):
            return False
        configured = Path(self.database_url[len(prefix):]).expanduser().resolve(strict=False)
        expected = (self.data_dir / "ai_tavern.db").expanduser().resolve(strict=False)
        return os.path.normcase(str(configured)) == os.path.normcase(str(expected))

    @property
    def allowed_host_items(self) -> tuple[str, ...]:
        return _csv_items(self.allowed_hosts)

    @property
    def cors_origin_items(self) -> tuple[str, ...]:
        return _csv_items(self.cors_origins)

    @property
    def llm_allowed_host_items(self) -> tuple[str, ...]:
        return _csv_items(self.llm_allowed_hosts)

    @property
    def auth_exempt_paths(self) -> tuple[str, ...]:
        return _csv_items(self.auth_exempt_paths_csv)

    @property
    def ai_rate_limit_paths(self) -> tuple[str, ...]:
        return (
            "/api/chat/stream",
            "/api/chat/regenerate",
            "/api/settings/test-connection",
        )

    def validate_runtime_security(self) -> None:
        if self.max_upload_size_mb <= 0:
            raise RuntimeError("AI_TAVERN_MAX_UPLOAD_SIZE_MB 必须大于 0")
        if self.max_backup_size_mb <= 0 or self.max_backup_uncompressed_mb <= 0:
            raise RuntimeError("备份大小限制必须大于 0")
        if self.max_backup_entries <= 0:
            raise RuntimeError("AI_TAVERN_MAX_BACKUP_ENTRIES 必须大于 0")
        if self.max_json_body_bytes <= 0 or self.max_request_body_bytes <= 0:
            raise RuntimeError("请求体限制必须大于 0")
        if self.max_concurrent_generations <= 0:
            raise RuntimeError("AI_TAVERN_MAX_CONCURRENT_GENERATIONS 必须大于 0")

        if not self.is_production:
            return

        password = self.auth_password.get_secret_value()
        if not self.auth_enabled:
            raise RuntimeError("生产环境必须设置 AI_TAVERN_AUTH_ENABLED=true")
        if not self.auth_username.strip():
            raise RuntimeError("生产环境必须设置 AI_TAVERN_AUTH_USERNAME")
        if len(password) < 12:
            raise RuntimeError("生产环境访问密码至少需要 12 个字符")
        weak_markers = {"password", "changeme", "change-me", "admin123456789"}
        if password.strip().lower() in weak_markers or "replace-with" in password.lower():
            raise RuntimeError("生产环境访问密码仍是示例值或弱密码")

        hosts = self.allowed_host_items
        if not hosts or "*" in hosts:
            raise RuntimeError("生产环境必须设置明确的 AI_TAVERN_ALLOWED_HOSTS，不能使用通配符")
        external_hosts = [
            host.lower() for host in hosts
            if host.lower() not in {"localhost", "127.0.0.1", "::1", "testserver"}
        ]
        if not external_hosts:
            raise RuntimeError("生产环境可信 Host 中必须包含实际访问域名")
        if all(host.endswith((".example.com", ".example.net", ".example.org", ".invalid", ".test")) for host in external_hosts):
            raise RuntimeError("生产环境可信 Host 仍是示例域名")
        if not self.rate_limit_enabled:
            raise RuntimeError("生产环境必须设置 AI_TAVERN_RATE_LIMIT_ENABLED=true")
        if self.enable_diagnostics:
            raise RuntimeError("生产环境默认应设置 AI_TAVERN_ENABLE_DIAGNOSTICS=false")
        if self.enable_selftest:
            raise RuntimeError("生产环境默认应设置 AI_TAVERN_ENABLE_SELFTEST=false")

    def ensure_directories(self):
        for directory in [
            self.data_dir,
            self.characters_dir,
            self.avatars_dir,
            self.exports_dir,
            self.backups_dir,
            self.logs_dir,
            self.diagnostics_dir,
            self.secrets_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)


settings = Settings()
