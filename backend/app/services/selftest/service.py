from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4
import zipfile

from ...core.config import settings
from ..diagnostics.service import diagnostic_service


class SelfTestService:
    def __init__(self, root_dir: Path):
        self._lock = RLock()
        self.root_dir = Path(root_dir)
        self._ensure_directory()
        self.cleanup_expired()

    def reconfigure(self, root_dir: Path) -> None:
        with self._lock:
            self.root_dir = Path(root_dir)
            self._ensure_directory()

    def _ensure_directory(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        if not run_id or any(char not in "0123456789abcdef" for char in run_id.lower()):
            raise ValueError("无效的自检运行编号")
        return self.root_dir / f"{run_id}.json"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _overall_status(payload: Mapping[str, Any]) -> str:
        statuses = [
            payload.get("backend", {}).get("status") if isinstance(payload.get("backend"), Mapping) else None,
            payload.get("frontend", {}).get("status") if isinstance(payload.get("frontend"), Mapping) else None,
        ]
        if any(status == "failed" for status in statuses):
            return "failed"
        if statuses and all(status == "passed" for status in statuses):
            return "passed"
        if any(status == "running" for status in statuses):
            return "running"
        return "waiting"

    def create_run(self) -> dict[str, Any]:
        run_id = uuid4().hex[:16]
        payload: dict[str, Any] = {
            "run_id": run_id,
            "created_at": self._now(),
            "updated_at": self._now(),
            "status": "waiting",
            "backend": None,
            "frontend": None,
            "context": {},
        }
        self._write(payload)
        return payload

    def _write(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        safe = diagnostic_service.redact_payload(dict(payload))
        run_id = str(safe.get("run_id", ""))
        safe["status"] = self._overall_status(safe)
        safe["updated_at"] = self._now()
        path = self._path(run_id)
        self._ensure_directory()
        path.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
        return safe

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        path = self._path(run_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        payload["status"] = self._overall_status(payload)
        return payload

    def update_component(self, run_id: str, component: str, report: Mapping[str, Any]) -> dict[str, Any]:
        if component not in {"backend", "frontend", "context"}:
            raise ValueError("未知的自检组件")
        with self._lock:
            payload = self.get_run(run_id)
            if payload is None:
                raise FileNotFoundError(run_id)
            payload[component] = diagnostic_service.redact_payload(dict(report))
            return self._write(payload)

    def build_export_bytes(self, run_id: str, diagnostics_bundle: bytes) -> bytes:
        payload = self.get_run(run_id)
        if payload is None:
            raise FileNotFoundError(run_id)
        summary = {
            "run_id": payload["run_id"],
            "status": payload.get("status", "waiting"),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
            "backend_status": (payload.get("backend") or {}).get("status"),
            "frontend_status": (payload.get("frontend") or {}).get("status"),
        }
        readme = (
            "AI Tavern one-click self-test bundle\n"
            "Upload this ZIP when requesting troubleshooting help.\n"
            "Reports and nested diagnostics are sanitized and exclude full API keys, prompts, chat bodies, and role-card contents.\n"
        )
        archive = BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("README.txt", readme)
            bundle.writestr("self-test-summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
            bundle.writestr("backend-tests.json", json.dumps(payload.get("backend"), ensure_ascii=False, indent=2))
            bundle.writestr("frontend-tests.json", json.dumps(payload.get("frontend"), ensure_ascii=False, indent=2))
            bundle.writestr("context.json", json.dumps(payload.get("context") or {}, ensure_ascii=False, indent=2))
            bundle.writestr("diagnostics.zip", diagnostics_bundle)
        return archive.getvalue()

    def cleanup_expired(self, retention_days: int = 3) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))
        self._ensure_directory()
        for path in self.root_dir.glob("*.json"):
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                if modified < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                continue


selftest_service = SelfTestService(settings.data_dir / "selftest")
