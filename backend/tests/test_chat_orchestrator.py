from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.db.models import Message
from app.db.session import get_db
from app.main import create_app
from app.services.settings_service import SettingsService


def make_client(db):
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def session_message_count(db, session_id: str) -> int:
    return (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .count()
    )


def test_incomplete_real_provider_configuration_is_422_without_pending_messages(
    db_with_session,
):
    db, _character, session = db_with_session
    SettingsService.update_settings(
        db,
        {
            "mock_llm": False,
            "clear_api_key": True,
            "base_url": "",
            "model": "",
        },
    )
    before = session_message_count(db, session.id)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "不应写入"},
    )

    assert response.status_code == 422
    assert "真实模型配置不完整" in response.json()["detail"]
    assert session_message_count(db, session.id) == before
    assert chat_api._active_streams == {}


def test_unsafe_real_provider_url_is_422_without_pending_messages(db_with_session):
    db, _character, session = db_with_session
    SettingsService.update_settings(
        db,
        {
            "mock_llm": False,
            "base_url": "http://localhost:9000",
            "api_key": "provider-secret",
            "model": "test-model",
        },
    )
    before = session_message_count(db, session.id)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "不应写入"},
    )

    assert response.status_code == 422
    assert "内部域名" in response.json()["detail"]
    assert "provider-secret" not in response.text
    assert session_message_count(db, session.id) == before


def test_unexpected_provider_initialization_failure_is_503_without_pending_messages(
    db_with_session,
    monkeypatch,
):
    db, _character, session = db_with_session
    before = session_message_count(db, session.id)

    def fail_provider(**_kwargs):
        raise RuntimeError("unexpected provider factory failure")

    monkeypatch.setattr(chat_api, "get_provider", fail_provider)
    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "不应写入"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "模型服务初始化失败，请检查模型设置后重试"
    assert session_message_count(db, session.id) == before


class FailingStreamProvider:
    _cancelled = False

    @property
    def cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True

    async def chat_completion(self, messages, **kwargs):
        if False:
            yield ""
        raise RuntimeError("upstream failed")


def test_active_stream_registry_is_cleaned_after_provider_error(
    db_with_session,
    monkeypatch,
):
    db, _character, session = db_with_session
    monkeypatch.setattr(
        chat_api,
        "get_provider",
        lambda **_kwargs: FailingStreamProvider(),
    )

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "触发上游错误"},
    )

    assert response.status_code == 200
    assert '"type": "error"' in response.text
    assert chat_api._active_streams == {}

class IdleProvider:
    _cancelled = False

    @property
    def cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True

    async def chat_completion(self, messages, **kwargs):
        yield "不会执行到这里"


async def _close_after_first_event(db, session_id: str):
    from app.services.chat import ChatOrchestrator
    from app.schemas import ChatRequest

    active_streams = {}
    orchestrator = ChatOrchestrator(
        db,
        provider_factory=lambda **_kwargs: IdleProvider(),
        active_streams=active_streams,
        active_sessions={},
        max_concurrent_generations=2,
    )
    prepared = orchestrator.prepare_stream(
        ChatRequest(session_id=session_id, message="提前关闭")
    )
    await anext(prepared.events)
    await prepared.events.aclose()
    return active_streams


def test_closing_stream_after_first_event_marks_message_stopped_and_cleans_registry(
    db_with_session,
):
    import asyncio

    db, _character, session = db_with_session
    active_streams = asyncio.run(_close_after_first_event(db, session.id))
    db.expire_all()
    assistant = (
        db.query(Message)
        .filter(Message.session_id == session.id, Message.role == "assistant")
        .order_by(Message.sequence.desc())
        .first()
    )

    assert assistant.generation_status == "stopped"
    assert active_streams == {}


def test_same_session_rejects_second_active_generation(db_with_session, monkeypatch):
    from app.services.chat import ChatOrchestrator, ChatServiceError
    from app.schemas import ChatRequest

    db, _character, session = db_with_session
    active_streams = {}
    active_sessions = {session.id: 'existing-message'}
    orchestrator = ChatOrchestrator(
        db,
        provider_factory=lambda **_kwargs: IdleProvider(),
        active_streams=active_streams,
        active_sessions=active_sessions,
        max_concurrent_generations=2,
    )
    try:
        orchestrator.prepare_stream(ChatRequest(session_id=session.id, message='重复请求'))
    except ChatServiceError as error:
        assert error.status_code == 409
    else:
        raise AssertionError('same-session generation was not rejected')
