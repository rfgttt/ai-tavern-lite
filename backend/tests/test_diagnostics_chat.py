import json

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import create_app


def make_client(db):
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data: ") and line[6:] != "[DONE]":
            events.append(json.loads(line[6:]))
    return events


class Provider:
    def __init__(self, chunks, cancelled=False, error=None):
        self.chunks = chunks
        self._cancelled = cancelled
        self.error = error

    @property
    def cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True

    async def chat_completion(self, messages, **kwargs):
        if self.error:
            raise self.error
        for chunk in self.chunks:
            yield chunk


def test_completed_chat_records_diagnostic_summary(db_with_session, monkeypatch, tmp_path):
    from app.services.diagnostics.service import diagnostic_service

    db, _char, session = db_with_session
    diagnostic_service.reconfigure(tmp_path / "logs", tmp_path / "diagnostics")
    monkeypatch.setattr(
        "app.api.chat.get_provider",
        lambda **kwargs: Provider(["你好", '<tavern_state>{"patch":[]}</tavern_state>']),
    )

    response = make_client(db).post("/api/chat/stream", json={"session_id": session.id, "message": "测试"})
    events = parse_sse(response.text)
    done = next(event for event in events if event["type"] == "done")
    latest = diagnostic_service.get_latest_request()

    assert response.status_code == 200
    assert done["request_id"] == latest["request_id"]
    assert latest["status"] == "complete"
    assert latest["timing"]["total_ms"] >= 0
    assert latest["generation"]["chunks"] == 2
    assert latest["prompt"]["worldbook_entries"] >= 1
    assert latest["state"]["patch_applied"] is False
    assert latest["state"]["state_changed"] is False
    assert latest["state"]["state_update_source"] == "none"
    assert "content" not in latest


def test_stopped_chat_records_stopped_status(db_with_session, monkeypatch, tmp_path):
    from app.services.diagnostics.service import diagnostic_service

    db, _char, session = db_with_session
    diagnostic_service.reconfigure(tmp_path / "logs", tmp_path / "diagnostics")
    provider = Provider(["部分"])
    provider._cancelled = True
    monkeypatch.setattr("app.api.chat.get_provider", lambda **kwargs: provider)

    response = make_client(db).post("/api/chat/stream", json={"session_id": session.id, "message": "停止"})
    done = next(event for event in parse_sse(response.text) if event["type"] == "done")
    latest = diagnostic_service.get_latest_request()

    assert done["status"] == "stopped"
    assert latest["status"] == "stopped"
    assert latest["state"]["patch_applied"] is False


def test_failed_chat_records_safe_error_type(db_with_session, monkeypatch, tmp_path):
    from app.services.diagnostics.service import diagnostic_service

    db, _char, session = db_with_session
    diagnostic_service.reconfigure(tmp_path / "logs", tmp_path / "diagnostics")
    monkeypatch.setattr(
        "app.api.chat.get_provider",
        lambda **kwargs: Provider([], error=RuntimeError("Bearer sk-sensitive-key request failed")),
    )

    response = make_client(db).post("/api/chat/stream", json={"session_id": session.id, "message": "失败"})
    latest = diagnostic_service.get_latest_request()

    assert response.status_code == 200
    assert latest["status"] == "error"
    assert latest["error"]["type"] == "RuntimeError"
    assert "sensitive-key" not in json.dumps(latest)
