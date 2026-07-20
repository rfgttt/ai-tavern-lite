import json

from fastapi.testclient import TestClient

from app.db.models import Character, ChatSession, Message
from app.db.session import get_db
from app.main import create_app


def make_client(db):
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_create_session_initializes_runtime_state(db_with_character):
    db, char = db_with_character
    client = make_client(db)

    response = client.post("/api/sessions", json={"character_id": char.id, "title": "沉浸测试"})
    assert response.status_code == 200
    session_id = response.json()["id"]

    runtime_response = client.get(f"/api/sessions/{session_id}/runtime")
    assert runtime_response.status_code == 200
    runtime = runtime_response.json()
    assert runtime["session_id"] == session_id
    assert runtime["profile"]["script_execution"] == "disabled"
    assert runtime["state"]["scene"]["location"] == "图书馆场景"
    assert runtime["profile"]["capabilities"]["formal_state_schema"] is True
    assert runtime["profile"]["state_schema"]["schema"] == "ai-tavern-state-schema/1"
    assert runtime["schema_validation"]["valid"] is True
    assert runtime["revision"] == 0


def test_character_runtime_profile_endpoint(db_with_character):
    db, char = db_with_character
    response = make_client(db).get(f"/api/characters/{char.id}/runtime-profile")

    assert response.status_code == 200
    payload = response.json()
    assert payload["card_spec"] == "chara_card_v3"
    assert payload["capabilities"]["worldbook"] is True


def test_runtime_state_can_be_replaced_safely(db_with_session):
    db, _char, session = db_with_session
    client = make_client(db)

    before = client.get(f"/api/sessions/{session.id}/runtime").json()
    state = before["state"]
    state["scene"]["location"] = "禁书区"

    response = client.put(f"/api/sessions/{session.id}/runtime/state", json={"state": state})

    assert response.status_code == 200
    assert response.json()["state"]["scene"]["location"] == "禁书区"
    assert response.json()["revision"] == 1



def test_runtime_state_replacement_rejects_schema_type_mismatch(db_with_session):
    db, _char, session = db_with_session
    client = make_client(db)

    state = client.get(f"/api/sessions/{session.id}/runtime").json()["state"]
    state["relationship"]["trust"] = "完全信任"

    response = client.put(f"/api/sessions/{session.id}/runtime/state", json={"state": state})

    assert response.status_code == 400
    assert "状态 Schema 校验失败" in response.json()["detail"]
    assert "期望 integer" in response.json()["detail"]

def test_timeline_and_rollback_restore_snapshot_state(db_with_session):
    from app.db.models import SessionState, TurnSnapshot
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.state_engine import build_initial_state

    db, char, session = db_with_session
    profile = analyze_card(json.loads(char.normalized_json))
    initial = build_initial_state(profile, json.loads(char.normalized_json))
    current = json.loads(json.dumps(initial, ensure_ascii=False))
    current["relationship"]["trust"] = 5
    runtime = SessionState(
        session_id=session.id,
        profile_json=json.dumps(profile, ensure_ascii=False),
        initial_state_json=json.dumps(initial, ensure_ascii=False),
        state_json=json.dumps(current, ensure_ascii=False),
        revision=2,
    )
    db.add(runtime)

    first = Message(session_id=session.id, role="assistant", content="第一回合", sequence=2, generation_status="complete")
    second = Message(session_id=session.id, role="assistant", content="第二回合", sequence=3, generation_status="complete")
    db.add_all([first, second])
    db.flush()
    second_id = second.id

    state_one = json.loads(json.dumps(initial, ensure_ascii=False))
    state_one["relationship"]["trust"] = 2
    db.add(TurnSnapshot(
        session_id=session.id,
        message_id=first.id,
        state_before_json=json.dumps(initial, ensure_ascii=False),
        patch_json='[{"op":"delta","path":"/relationship/trust","value":2}]',
        state_after_json=json.dumps(state_one, ensure_ascii=False),
        events_json='["第一次建立信任"]',
        choices_json='["继续交谈"]',
        dice_json='[]',
        battle_checks_json='[]',
        battle_json='null',
        triggered_lorebook_json='[]',
        rejected_patch_json='[]',
        decision_trace_json=json.dumps([{
            "operation_id": "op-001",
            "alias": {"reason_code": "ALIAS_CONFIRMED"},
            "apply": {"decision": "applied", "reason_code": "APPLIED", "changed": True},
        }], ensure_ascii=False),
    ))
    db.add(TurnSnapshot(
        session_id=session.id,
        message_id=second.id,
        state_before_json=json.dumps(state_one, ensure_ascii=False),
        patch_json='[{"op":"delta","path":"/relationship/trust","value":3}]',
        state_after_json=json.dumps(current, ensure_ascii=False),
        events_json='["信任加深"]',
        choices_json='[]',
        dice_json='[]',
        battle_checks_json='[]',
        battle_json='null',
        triggered_lorebook_json='[]',
        rejected_patch_json='[]',
        decision_trace_json=json.dumps([{
            "operation_id": "op-001",
            "alias": {"reason_code": "ALIAS_NOT_NEEDED"},
            "apply": {"decision": "applied", "reason_code": "APPLIED", "changed": True},
        }], ensure_ascii=False),
    ))
    db.commit()

    client = make_client(db)
    timeline = client.get(f"/api/sessions/{session.id}/timeline")
    assert timeline.status_code == 200
    timeline_payload = timeline.json()
    assert [item["message_id"] for item in timeline_payload] == [first.id, second.id]
    assert timeline_payload[0]["decision_trace"][0]["alias"]["reason_code"] == "ALIAS_CONFIRMED"
    assert timeline_payload[1]["decision_trace"][0]["alias"]["reason_code"] == "ALIAS_NOT_NEEDED"

    runtime_payload = client.get(f"/api/sessions/{session.id}/runtime").json()
    assert runtime_payload["last_turn"]["decision_trace"][0]["apply"]["changed"] is True

    response = client.post(
        f"/api/sessions/{session.id}/rollback",
        json={"message_id": first.id},
    )
    assert response.status_code == 200
    assert response.json()["state"]["relationship"]["trust"] == 2
    assert db.query(Message).filter(Message.id == second_id).first() is None
    assert response.json()["revision"] == 3


def test_runtime_last_turn_uses_message_sequence_not_snapshot_id(db_with_session):
    from datetime import datetime

    from app.db.models import TurnSnapshot
    from app.services.runtime.session_service import ensure_session_state

    db, char, session = db_with_session
    ensure_session_state(db, session, char)
    first = Message(id="message-first", session_id=session.id, role="assistant", content="第一回合", sequence=2, generation_status="complete")
    second = Message(id="message-second", session_id=session.id, role="assistant", content="第二回合", sequence=3, generation_status="complete")
    db.add_all([first, second])
    db.flush()
    same_time = datetime(2026, 7, 14, 12, 0, 0)
    db.add_all([
        TurnSnapshot(
            id="snapshot-z-first",
            session_id=session.id,
            message_id=first.id,
            state_before_json="{}",
            state_after_json="{}",
            events_json='["first"]',
            created_at=same_time,
        ),
        TurnSnapshot(
            id="snapshot-a-second",
            session_id=session.id,
            message_id=second.id,
            state_before_json="{}",
            state_after_json="{}",
            events_json='["second"]',
            created_at=same_time,
        ),
    ])
    db.commit()

    payload = make_client(db).get(f"/api/sessions/{session.id}/runtime").json()

    assert payload["last_turn"]["message_id"] == second.id
