import json

from fastapi.testclient import TestClient

from app.db.models import Message, SessionState, TurnSnapshot
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
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            continue
        events.append(json.loads(payload))
    return events


class Provider:
    def __init__(self, chunks, cancel=False):
        self.chunks = chunks
        self._cancelled = False
        self.cancel_after = cancel
        self.messages = None

    @property
    def cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True

    async def chat_completion(self, messages, **kwargs):
        self.messages = messages
        for index, chunk in enumerate(self.chunks):
            yield chunk
            if self.cancel_after and index == 0:
                self._cancelled = True
                break


def test_chat_applies_hidden_state_and_emits_native_runtime(db_with_session, monkeypatch):
    db, _char, session = db_with_session
    provider = Provider([
        "她认真地点了点头。\n<tavern_",
        'state>{"patch":[{"op":"delta","path":"/relationship/trust","value":2}],',
        '"events":["建立了初步信任"],"choices":["询问禁书区","换个话题"],"expression":"认真"}</tavern_state>',
    ])
    monkeypatch.setattr("app.api.chat.get_provider", lambda **kwargs: provider)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "我会遵守规则。"},
    )
    assert response.status_code == 200
    events = parse_sse(response.text)

    content = "".join(event.get("content", "") for event in events if event.get("type") == "content")
    assert content == "她认真地点了点头。\n"
    assert "tavern_state" not in content

    runtime_event = next(event for event in events if event.get("type") == "runtime")
    done = next(event for event in events if event.get("type") == "done")
    assert runtime_event["state"]["relationship"]["trust"] == 0
    assert done["content"] == "她认真地点了点头。"
    assert done["runtime"]["state_after"]["relationship"]["trust"] == 2
    assert done["runtime"]["choices"] == ["询问禁书区", "换个话题"]
    assert done["runtime"]["expression"] == "认真"

    assistant = db.query(Message).filter(Message.id == done["message_id"]).one()
    state = db.query(SessionState).filter(SessionState.session_id == session.id).one()
    snapshot = db.query(TurnSnapshot).filter(TurnSnapshot.message_id == assistant.id).one()
    assert assistant.content == "她认真地点了点头。"
    assert json.loads(state.state_json)["relationship"]["trust"] == 2
    assert json.loads(snapshot.events_json) == ["建立了初步信任"]


def test_chat_converts_dice_and_battle_blocks_to_metadata(db_with_session, monkeypatch):
    db, _char, session = db_with_session
    provider = Provider([
        "箭矢命中目标。\n",
        "<dice>\n发动技能: 远程攻击\n目标: 哥布林\n情境: 走廊伏击\n检定细节: d20(15)+5=20 vs AC13\n判定结果: 成功（Success）\n结果描述: 命中\n</dice>",
        "<battle>\n玩家|init 18|hp 8/10|pos 0,0|att 0|next\n哥布林|init 10|hp 3/7|pos 10,0|att 2\n</battle>",
    ])
    monkeypatch.setattr("app.api.chat.get_provider", lambda **kwargs: provider)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "射击"},
    )
    done = next(event for event in parse_sse(response.text) if event.get("type") == "done")

    assert done["content"] == "箭矢命中目标。"
    assert done["runtime"]["dice"][0]["skill"] == "远程攻击"
    assert done["runtime"]["battle"]["units"][1]["id"] == "哥布林"
    assert done["runtime"]["state_after"]["combat"]["active"] is True


def test_stopped_generation_does_not_apply_partial_state(db_with_session, monkeypatch):
    db, _char, session = db_with_session
    provider = Provider([
        '半句话<tavern_state>{"patch":[{"op":"delta","path":"/relationship/trust","value":50}]}',
        "</tavern_state>",
    ], cancel=True)
    monkeypatch.setattr("app.api.chat.get_provider", lambda **kwargs: provider)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "停止"},
    )
    done = next(event for event in parse_sse(response.text) if event.get("type") == "done")
    runtime = make_client(db).get(f"/api/sessions/{session.id}/runtime").json()

    assert done["status"] == "stopped"
    assert runtime["state"]["relationship"]["trust"] == 0
    assert db.query(TurnSnapshot).filter(TurnSnapshot.message_id == done["message_id"]).first() is None


def test_regenerate_restores_state_before_old_turn(db_with_session, monkeypatch):
    db, _char, session = db_with_session
    providers = [
        Provider(['第一版<tavern_state>{"patch":[{"op":"delta","path":"/relationship/trust","value":5}]}</tavern_state>']),
        Provider(['第二版<tavern_state>{"patch":[]}</tavern_state>']),
    ]
    monkeypatch.setattr("app.api.chat.get_provider", lambda **kwargs: providers.pop(0))
    client = make_client(db)

    first_response = client.post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "测试"},
    )
    first_done = next(event for event in parse_sse(first_response.text) if event.get("type") == "done")
    assert first_done["runtime"]["state_after"]["relationship"]["trust"] == 5

    regen_response = client.post(
        "/api/chat/regenerate",
        json={"session_id": session.id, "message": ""},
    )
    regen_done = next(event for event in parse_sse(regen_response.text) if event.get("type") == "done")

    assert regen_done["content"] == "第二版"
    assert regen_done["runtime"]["state_before"]["relationship"]["trust"] == 0
    runtime = client.get(f"/api/sessions/{session.id}/runtime").json()
    assert runtime["state"]["relationship"]["trust"] == 0
