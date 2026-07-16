from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _backend_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _default_database_url() -> str:
    return f"sqlite:///{(_backend_dir() / 'data' / 'ai_tavern.db').as_posix()}"


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
    data_dir: Path = base_dir / "data"
    characters_dir: Path = data_dir / "characters"
    avatars_dir: Path = data_dir / "avatars"
    exports_dir: Path = data_dir / "exports"
    backups_dir: Path = data_dir / "backups"
    logs_dir: Path = data_dir / "logs"
    diagnostics_dir: Path = data_dir / "diagnostics"

    environment: str = "development"
    database_url: str = _default_database_url()
    max_upload_size_mb: int = 20
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
    create_demo_data: bool = True

    frontend_dist_dir: Path = base_dir.parent / "frontend" / "dist"

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}

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
        ]:
            directory.mkdir(parents=True, exist_ok=True)


settings = Settings()
