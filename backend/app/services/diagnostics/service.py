from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import logging
from pathlib import Path
import platform
import re
import sys
from threading import RLock
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit
import zipfile

from ...core.config import settings


_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "secret",
)
_URL_KEYS = {"base_url", "url", "endpoint"}
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/=]{6,}"),
    re.compile(r"(?i)\b(sk-[A-Za-z0-9_\-]{6,})\b"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,;]+"),
)


class DiagnosticService:
    """Safe diagnostics persistence and export.

    This service deliberately records metadata only. It never needs prompt or response
    bodies, and all public write/export methods apply recursive redaction.
    """

    def __init__(self, logs_dir: Path, diagnostics_dir: Path):
        self._lock = RLock()
        self.logs_dir = Path(logs_dir)
        self.diagnostics_dir = Path(diagnostics_dir)
        self._latest_request: dict[str, Any] | None = None
        self._ensure_directories()
        self.cleanup_old_chat_logs()
        self._load_latest()

    @property
    def latest_path(self) -> Path:
        return self.diagnostics_dir / "latest-request.json"

    def reconfigure(self, logs_dir: Path, diagnostics_dir: Path) -> None:
        """Point the service at another storage root (primarily useful for tests)."""
        with self._lock:
            self.logs_dir = Path(logs_dir)
            self.diagnostics_dir = Path(diagnostics_dir)
            self._latest_request = None
            self._ensure_directories()
            self._load_latest()

    def _ensure_directories(self) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def mask_secret(value: Any) -> str:
        text = "" if value is None else str(value)
        if not text:
            return ""
        if len(text) <= 8:
            return "<redacted>"
        prefix = "sk-" if text.startswith("sk-") else ""
        suffix = text[-4:]
        return f"{prefix}****{suffix}"

    @staticmethod
    def sanitize_url(value: Any) -> str:
        text = "" if value is None else str(value).strip()
        if not text:
            return ""
        try:
            parsed = urlsplit(text)
            if not parsed.scheme or not parsed.netloc:
                return text.split("?", 1)[0].split("#", 1)[0]
            host = parsed.hostname or ""
            if parsed.port:
                host = f"{host}:{parsed.port}"
            return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))
        except (ValueError, TypeError):
            return text.split("?", 1)[0].split("#", 1)[0]

    @classmethod
    def sanitize_text(cls, value: Any, secrets: tuple[str, ...] = ()) -> str:
        text = "" if value is None else str(value)
        for secret in secrets:
            if secret:
                text = text.replace(secret, cls.mask_secret(secret))
        text = _URL_PATTERN.sub(lambda match: cls.sanitize_url(match.group(0)), text)
        for pattern in _SECRET_PATTERNS:
            if pattern.pattern.lower().startswith("(?i)(bearer"):
                text = pattern.sub(r"\1<redacted>", text)
            elif "api[_-]?key" in pattern.pattern:
                text = pattern.sub(r"\1<redacted>", text)
            else:
                text = pattern.sub(lambda match: cls.mask_secret(match.group(1)), text)
        return text

    @classmethod
    def redact_payload(cls, value: Any, parent_key: str = "") -> Any:
        if isinstance(value, Mapping):
            result: dict[str, Any] = {}
            for raw_key, item in value.items():
                key = str(raw_key)
                lower = key.lower()
                if lower in {"custom_headers", "headers", "request_headers"} and isinstance(item, Mapping):
                    result[key] = {str(header): "<redacted>" for header in item.keys()}
                elif any(part in lower for part in _SECRET_KEY_PARTS):
                    if lower == "api_key":
                        result[key] = cls.mask_secret(item)
                    else:
                        result[key] = "<redacted>"
                elif lower in _URL_KEYS or lower.endswith("_url"):
                    result[key] = cls.sanitize_url(item)
                else:
                    result[key] = cls.redact_payload(item, lower)
            return result
        if isinstance(value, (list, tuple, set)):
            return [cls.redact_payload(item, parent_key) for item in value]
        if isinstance(value, str):
            return cls.sanitize_text(value)
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return cls.sanitize_text(value)

    def _load_latest(self) -> None:
        if not self.latest_path.exists():
            return
        try:
            loaded = json.loads(self.latest_path.read_text("utf-8"))
            if isinstance(loaded, dict):
                self._latest_request = loaded
        except (OSError, json.JSONDecodeError):
            self._latest_request = None

    def record_chat_request(self, summary: Mapping[str, Any]) -> dict[str, Any]:
        safe = self.redact_payload(deepcopy(dict(summary)))
        safe.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
        with self._lock:
            try:
                self._ensure_directories()
                self._latest_request = safe
                self.latest_path.write_text(
                    json.dumps(safe, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                chat_path = self.logs_dir / f"chat-{datetime.now().strftime('%Y-%m-%d')}.jsonl"
                with chat_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(safe, ensure_ascii=False, separators=(",", ":")) + "\n")
            except OSError as error:
                logging.getLogger("ai_tavern").warning(
                    "Diagnostic request record failed: %s", self.sanitize_text(error)
                )
        return safe

    def get_latest_request(self) -> dict[str, Any] | None:
        with self._lock:
            return deepcopy(self._latest_request)

    def cleanup_old_chat_logs(self, retention_days: int = 7) -> None:
        cutoff = datetime.now() - timedelta(days=max(1, retention_days))
        try:
            self._ensure_directories()
            for path in self.logs_dir.glob("chat-*.jsonl"):
                try:
                    modified = datetime.fromtimestamp(path.stat().st_mtime)
                    if modified < cutoff:
                        path.unlink(missing_ok=True)
                except OSError:
                    continue
        except OSError:
            return

    def clear_logs(self) -> None:
        with self._lock:
            self._ensure_directories()
            for path in self.logs_dir.glob("chat-*.jsonl"):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            app_log = self.logs_dir / "app.log"
            try:
                app_log.write_text("", encoding="utf-8")
            except OSError:
                pass
            for path in self.logs_dir.glob("app.log.*"):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                self.latest_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._latest_request = None

    def log_writable(self) -> bool:
        probe = self.logs_dir / ".write-test"
        try:
            self._ensure_directories()
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def _tail_text(self, path: Path, max_bytes: int = 256_000) -> str:
        try:
            with path.open("rb") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                handle.seek(max(0, size - max_bytes))
                return handle.read().decode("utf-8", errors="replace")
        except OSError:
            return ""

    def system_info(self, version: str = "2.2.0-preview.1") -> dict[str, Any]:
        return {
            "app_version": version,
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "python_implementation": platform.python_implementation(),
        }

    @staticmethod
    def _json_bytes(payload: Any) -> bytes:
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    def build_export_bytes(
        self,
        *,
        health: Mapping[str, Any],
        system: Mapping[str, Any],
        settings_payload: Mapping[str, Any],
        database_summary: Mapping[str, Any],
    ) -> bytes:
        safe_health = self.redact_payload(dict(health))
        safe_system = self.redact_payload(dict(system))
        safe_settings = self.redact_payload(dict(settings_payload))
        safe_database = self.redact_payload(dict(database_summary))
        latest = self.get_latest_request()

        readme = (
            "AI Tavern diagnostic bundle\n"
            "Generated locally. This package contains metadata and redacted logs only.\n"
            "It intentionally excludes complete prompts, chat bodies, character cards, API keys, "
            "and custom request header values.\n"
        )
        archive = BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("README.txt", readme)
            bundle.writestr("health.json", self._json_bytes(safe_health))
            bundle.writestr("system.json", self._json_bytes(safe_system))
            bundle.writestr("settings-sanitized.json", self._json_bytes(safe_settings))
            bundle.writestr("database-summary.json", self._json_bytes(safe_database))
            bundle.writestr("latest-request.json", self._json_bytes(latest))

            app_log = self._tail_text(self.logs_dir / "app.log")
            if app_log:
                bundle.writestr("app.log", self.sanitize_text(app_log))
            chat_files = sorted(self.logs_dir.glob("chat-*.jsonl"))[-2:]
            for chat_path in chat_files:
                text = self._tail_text(chat_path)
                if text:
                    bundle.writestr(f"logs/{chat_path.name}", self.sanitize_text(text))
        return archive.getvalue()


diagnostic_service = DiagnosticService(settings.logs_dir, settings.diagnostics_dir)
