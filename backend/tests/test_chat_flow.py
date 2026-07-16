import pytest
import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.db.models import ChatSession, Message
from app.db.session import get_db
from app.main import create_app


def make_client(db):
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


class CaptureProvider:
    def __init__(self, chunks=("好",), cancel_after_first=False):
        self.messages = None
        self._cancelled = False
        self.chunks = chunks
        self.cancel_after_first = cancel_after_first

    @property
    def cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True

    async def chat_completion(self, messages, **kwargs):
        self.messages = messages
        for index, chunk in enumerate(self.chunks):
            yield chunk
            if self.cancel_after_first and index == 0:
                self._cancelled = True
                break


def parse_sse(response_text):
    events = []
    for line in response_text.splitlines():
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            events.append(data)
        else:
            events.append(json.loads(data))
    return events


def test_stream_sends_current_user_message_to_provider_once(db_with_session, monkeypatch):
    db, _char, session = db_with_session
    provider = CaptureProvider()
    monkeypatch.setattr("app.api.chat.get_provider", lambda **kwargs: provider)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "只出现一次"},
    )

    assert response.status_code == 200
    user_contents = [m["content"] for m in provider.messages if m["role"] == "user"]
    assert user_contents.count("只出现一次") == 1


def test_stream_emits_message_and_done_events(db_with_session, monkeypatch):
    db, _char, session = db_with_session
    provider = CaptureProvider(chunks=("你", "好"))
    monkeypatch.setattr("app.api.chat.get_provider", lambda **kwargs: provider)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "你好"},
    )
    events = parse_sse(response.text)

    message_event = next(event for event in events if isinstance(event, dict) and event.get("type") == "message")
    done_event = next(event for event in events if isinstance(event, dict) and event.get("type") == "done")
    assert message_event["user_message"]["content"] == "你好"
    assert message_event["assistant_message"]["generation_status"] == "generating"
    assert done_event["status"] == "complete"
    assert done_event["content"] == "你好"


def test_cancelled_provider_keeps_message_stopped(db_with_session, monkeypatch):
    db, _char, session = db_with_session
    provider = CaptureProvider(chunks=("一", "二"), cancel_after_first=True)
    monkeypatch.setattr("app.api.chat.get_provider", lambda **kwargs: provider)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "停止测试"},
    )
    events = parse_sse(response.text)
    done_event = next(event for event in events if isinstance(event, dict) and event.get("type") == "done")
    assistant = db.query(Message).filter(
        Message.session_id == session.id,
        Message.role == "assistant",
    ).order_by(Message.sequence.desc()).first()

    assert assistant.generation_status == "stopped"
    assert done_event["status"] == "stopped"


def test_adding_message_updates_session_activity(db_with_session):
    db, _char, session = db_with_session
    old_time = datetime.now() - timedelta(days=1)
    session.updated_at = old_time
    db.commit()

    response = make_client(db).post(
        f"/api/sessions/{session.id}/messages",
        json={"session_id": session.id, "role": "user", "content": "新消息", "sequence": 99},
    )

    assert response.status_code == 200
    db.refresh(session)
    assert session.updated_at > old_time
    assert response.json()["sequence"] == 2


def test_stop_endpoint_cancels_provider_and_marks_message_stopped(db_with_session):
    from app.api import chat as chat_api

    db, _char, session = db_with_session
    message = Message(
        session_id=session.id,
        role="assistant",
        content="部分内容",
        sequence=2,
        generation_status="generating",
    )
    db.add(message)
    db.commit()
    provider = CaptureProvider()
    chat_api._active_streams[message.id] = provider

    try:
        response = make_client(db).post("/api/chat/stop", json={"message_id": message.id})
        db.refresh(message)
        assert response.status_code == 200
        assert provider.cancelled is True
        assert message.generation_status == "stopped"
    finally:
        chat_api._active_streams.pop(message.id, None)


def test_regenerate_replaces_latest_assistant_in_database(db_with_session, monkeypatch):
    db, _char, session = db_with_session
    old_reply = Message(
        session_id=session.id,
        role="assistant",
        content="旧回复",
        sequence=2,
        generation_status="complete",
    )
    db.add(old_reply)
    db.commit()
    old_reply_id = old_reply.id

    provider = CaptureProvider(chunks=("新", "回复"))
    monkeypatch.setattr("app.api.chat.get_provider", lambda **kwargs: provider)
    response = make_client(db).post(
        "/api/chat/regenerate",
        json={"session_id": session.id, "message": ""},
    )

    assert response.status_code == 200
    messages = db.query(Message).filter(Message.session_id == session.id).order_by(Message.sequence).all()
    assert db.query(Message).filter(Message.id == old_reply_id).first() is None
    assert [message.content for message in messages if message.role == "assistant"] == [
        "*抬起头从书本中看向你* 欢迎来到图书馆。",
        "新回复",
    ]
    assert [message.content for message in messages if message.role == "user"] == [
        "你好，请问这里有魔法相关的书吗？"
    ]


@pytest.mark.asyncio
async def test_provider_cancel_before_iteration_is_not_lost():
    from app.services.llm.provider import MockLLMProvider

    provider = MockLLMProvider(character_name="测试")
    provider.cancel()
    chunks = [chunk async for chunk in provider.chat_completion(messages=[])]

    assert chunks == []
    assert provider.cancelled is True
