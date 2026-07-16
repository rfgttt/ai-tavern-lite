import json

import pytest
from fastapi.testclient import TestClient

from app.db.models import Message, TurnSnapshot
from app.db.session import get_db
from app.main import create_app
from app.services.llm.provider import MockLLMProvider, get_provider


def make_client(db):
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_editing_latest_message_rebuilds_render_segments(db_with_session):
    db, _character, session = db_with_session
    message = Message(
        session_id=session.id,
        role="assistant",
        content="旧内容",
        sequence=2,
        generation_status="complete",
        segments_json=json.dumps([{"type": "narration", "text": "旧内容"}], ensure_ascii=False),
    )
    db.add(message)
    db.commit()

    response = make_client(db).put(
        f"/api/messages/{message.id}",
        json={"content": "林夕：「新台词」"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["content"] == "林夕：「新台词」"
    assert payload["segments"][0]["type"] == "dialogue"
    assert payload["segments"][0]["speaker"] == "林夕"
    db.refresh(message)
    assert "旧内容" not in message.segments_json


def test_editing_message_with_later_history_is_blocked(db_with_session):
    db, _character, session = db_with_session
    earlier = db.query(Message).filter(Message.session_id == session.id).order_by(Message.sequence.asc()).first()
    response = make_client(db).put(
        f"/api/messages/{earlier.id}",
        json={"content": "改写过去"},
    )
    assert response.status_code == 409
    assert "之后已有剧情" in response.json()["detail"]


def test_deleting_user_message_with_later_history_is_blocked(db_with_session):
    db, _character, session = db_with_session
    user_message = db.query(Message).filter(
        Message.session_id == session.id,
        Message.role == "user",
    ).first()
    later = Message(
        session_id=session.id,
        role="assistant",
        content="后续结果",
        sequence=user_message.sequence + 1,
        generation_status="complete",
    )
    db.add(later)
    db.commit()

    response = make_client(db).delete(f"/api/messages/{user_message.id}")
    assert response.status_code == 409
    assert "之后已有剧情" in response.json()["detail"]


def test_real_provider_mode_never_silently_falls_back_to_mock():
    with pytest.raises(ValueError, match="真实模型配置不完整"):
        get_provider(mock_mode=False, base_url="", api_key="", model="")


def test_explicit_mock_mode_still_returns_mock_provider():
    provider = get_provider(mock_mode=True, character_name="测试")
    assert isinstance(provider, MockLLMProvider)


def test_new_session_greeting_has_initial_state_snapshot(test_db, sample_v3_character_json):
    from app.db.models import Character

    character = Character(
        name="开场快照角色",
        first_message="你好<StatusPlaceHolderImpl/>",
        normalized_json=json.dumps(sample_v3_character_json["data"], ensure_ascii=False),
    )
    test_db.add(character)
    test_db.commit()

    response = make_client(test_db).post(
        "/api/sessions",
        json={"character_id": character.id, "title": "初始状态"},
    )
    assert response.status_code == 200
    session_id = response.json()["id"]
    greeting = test_db.query(Message).filter(Message.session_id == session_id).first()
    snapshot = test_db.query(TurnSnapshot).filter(TurnSnapshot.message_id == greeting.id).first()
    assert snapshot is not None
    assert json.loads(snapshot.state_before_json) == json.loads(snapshot.state_after_json)

class FailingProvider:
    _cancelled = False

    @property
    def cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True

    async def chat_completion(self, messages, **kwargs):
        if False:
            yield ""
        raise RuntimeError("upstream unavailable")


def test_failed_regeneration_preserves_last_good_reply(db_with_session, monkeypatch):
    db, _character, session = db_with_session
    old_reply = Message(
        session_id=session.id,
        role="assistant",
        content="不能丢失的旧回复",
        sequence=2,
        generation_status="complete",
    )
    db.add(old_reply)
    db.commit()
    old_id = old_reply.id

    monkeypatch.setattr("app.api.chat.get_provider", lambda **kwargs: FailingProvider())
    response = make_client(db).post(
        "/api/chat/regenerate",
        json={"session_id": session.id, "message": ""},
    )

    assert response.status_code == 200
    db.expire_all()
    persisted = db.query(Message).filter(Message.id == old_id).first()
    assert persisted is not None
    assert persisted.content == "不能丢失的旧回复"
    assistants = db.query(Message).filter(
        Message.session_id == session.id,
        Message.role == "assistant",
    ).all()
    assert all(message.generation_status != "error" for message in assistants)
