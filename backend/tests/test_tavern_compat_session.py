import json

from app.db.models import Character, ChatSession
from app.services.runtime.session_service import ensure_session_state
from app.services.runtime.state_engine import apply_patch


def test_session_initializes_disabled_initvar_and_accepts_replace(test_db):
    normalized = {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "name": "通用 MVU 角色",
        "description": "",
        "scenario": "",
        "extensions": {},
        "character_book": {
            "entries": [
                {
                    "comment": "[initvar]",
                    "enabled": False,
                    "content": "世界信息:\n  当前地点: 教室\n角色甲:\n  好感度: 20",
                },
                {
                    "comment": "变量输出格式",
                    "enabled": True,
                    "constant": True,
                    "content": "<UpdateVariable><JSONPatch>",
                },
            ]
        },
    }
    character = Character(
        name="通用 MVU 角色",
        normalized_json=json.dumps(normalized, ensure_ascii=False),
        raw_json=json.dumps({"data": normalized}, ensure_ascii=False),
    )
    test_db.add(character)
    test_db.flush()
    session = ChatSession(character_id=character.id, title="MVU")
    test_db.add(session)
    test_db.flush()

    runtime = ensure_session_state(test_db, session, character)
    state = json.loads(runtime.state_json)

    assert state["custom"]["世界信息"]["当前地点"] == "教室"
    assert state["custom"]["角色甲"]["好感度"] == 20

    result = apply_patch(state, [{"op": "replace", "path": "/custom/角色甲/好感度", "value": 21}])
    assert result.rejected == []
    assert result.state["custom"]["角色甲"]["好感度"] == 21


def test_custom_patch_refreshes_projected_relationship(test_db):
    from app.services.runtime.state_engine import apply_patch

    state = {
        'scene': {}, 'relationship': {'affection': 20}, 'character': {'name': '角色甲'},
        'custom': {'角色甲': {'好感度': 20}},
    }
    result = apply_patch(state, [
        {'op': 'replace', 'path': '/custom/角色甲/好感度', 'value': 24},
    ])
    assert result.rejected == []
    assert result.state['relationship']['affection'] == 24


def test_existing_session_backfills_new_card_variables_without_overwriting_progress(test_db):
    from app.db.models import SessionState

    normalized = {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "name": "升级角色",
        "extensions": {},
        "character_book": {"entries": [
            {
                "comment": "[initvar]",
                "enabled": False,
                "content": (
                    "world_state:\n"
                    "  location: Old Harbor\n"
                    "升级角色:\n"
                    "  affection: 20\n"
                    "  mood: calm\n"
                    "  keepsakes:\n"
                    "    compass:\n"
                    "      note: inherited\n"
                ),
            },
            {"comment": "Variable protocol", "enabled": True, "content": "<UpdateVariable><JSONPatch>"},
        ]},
    }
    character = Character(
        name="升级角色",
        normalized_json=json.dumps(normalized, ensure_ascii=False),
        raw_json=json.dumps({"data": normalized}, ensure_ascii=False),
    )
    test_db.add(character)
    test_db.flush()
    session = ChatSession(character_id=character.id, title="旧会话")
    test_db.add(session)
    test_db.flush()
    runtime = SessionState(
        session_id=session.id,
        profile_json=json.dumps({"version": 2}, ensure_ascii=False),
        initial_state_json=json.dumps({"custom": {}, "character": {"name": "升级角色"}}, ensure_ascii=False),
        state_json=json.dumps({
            "custom": {"升级角色": {"affection": 37}},
            "character": {"name": "升级角色"},
            "relationship": {"affection": 37},
        }, ensure_ascii=False),
        revision=9,
    )
    test_db.add(runtime)
    test_db.flush()

    migrated = ensure_session_state(test_db, session, character)
    initial_state = json.loads(migrated.initial_state_json)
    current_state = json.loads(migrated.state_json)
    profile = json.loads(migrated.profile_json)

    assert profile["version"] == 3
    assert initial_state["custom"]["升级角色"]["affection"] == 20
    assert initial_state["custom"]["升级角色"]["keepsakes"]["compass"]["note"] == "inherited"
    assert current_state["custom"]["升级角色"]["affection"] == 37
    assert current_state["custom"]["升级角色"]["mood"] == "calm"
    assert current_state["scene"]["location"] == "Old Harbor"
    assert current_state["relationship"]["affection"] == 37
    assert migrated.revision == 9
