import json

from fastapi.testclient import TestClient

from app.db.models import Character, CharacterStateAlias
from app.db.session import get_db
from app.main import create_app
from app.services.runtime.card_profile import analyze_card
from app.services.runtime.state_aliases import (
    ALIAS_REGISTRY_ID,
    build_alias_registry,
    normalize_alias_operations,
)
from app.services.runtime.state_engine import apply_patch
from app.services.runtime.state_schema import build_state_schema


def _state_and_schema():
    state = {
        "runtime_version": 2,
        "mode": "relationship",
        "scene": {},
        "character": {"name": "穗秋生"},
        "relationship": {"affection": 5, "fear": 95, "dependence": 100},
        "player": {"name": "用户"},
        "party": [],
        "quests": [],
        "inventory": [],
        "combat": {},
        "custom": {
            "$meta": {"strictSet": True, "extensible": False},
            "穗秋生": {
                "$meta": {"extensible": False, "required": ["好感度", "害怕值", "依赖值"]},
                "好感度": [5, "[0-100]好感"],
                "害怕值": [95, "[0-100]恐惧"],
                "依赖值": [100, "[0-100]依赖"],
            },
        },
    }
    policy = {
        "relationship_paths": {
            "affection": ["/custom/穗秋生/好感度/0", "/relationship/affection"],
            "fear": ["/custom/穗秋生/害怕值/0", "/relationship/fear"],
            "dependence": ["/custom/穗秋生/依赖值/0", "/relationship/dependence"],
        }
    }
    return state, build_state_schema(state, policy=policy)


def _client(db):
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_registry_suggestions_are_not_active_until_confirmed():
    state, schema = _state_and_schema()
    registry = build_alias_registry(schema)
    assert registry["schema"] == ALIAS_REGISTRY_ID
    assert any(item["alias_key"] == "favor" for item in registry["suggestions"])

    raw = [{"op": "increment", "path": "/custom/穗秋生/favor/0", "value": 1}]
    alias_result = normalize_alias_operations(raw, schema, registry)
    assert alias_result.operations == raw
    assert alias_result.events[0]["reason_code"] == "ALIAS_CONFIRMATION_REQUIRED"

    result = apply_patch(state, raw, schema=schema, aliases=registry)
    assert result.applied == []
    assert result.rejected
    assert result.alias_events[0]["decision"] == "suggested"


def test_confirmed_alias_writes_to_card_canonical_path():
    state, schema = _state_and_schema()
    registry = build_alias_registry(schema, confirmed_rows=[{
        "id": "a1",
        "alias": "favor",
        "alias_key": "favor",
        "semantic": "relationship.affection",
        "canonical_path": "/relationship/affection",
        "source": "user_confirmed",
        "confidence": 1.0,
    }])

    raw = [{"op": "increment", "path": "/custom/穗秋生/favor/0", "value": 1}]
    alias_result = normalize_alias_operations(raw, schema, registry)
    assert alias_result.operations[0]["path"] == "/custom/穗秋生/好感度/0"
    assert alias_result.events[0]["reason_code"] == "ALIAS_CONFIRMED"

    result = apply_patch(state, raw, schema=schema, aliases=registry)
    assert result.applied[0]["path"] == "/custom/穗秋生/好感度/0"
    assert result.state["custom"]["穗秋生"]["好感度"][0] == 6
    assert result.state["relationship"]["affection"] == 6


def test_declared_path_cannot_be_shadowed_by_alias():
    state, schema = _state_and_schema()
    registry = build_alias_registry(schema, confirmed_rows=[{
        "id": "a1",
        "alias": "affection",
        "alias_key": "affection",
        "semantic": "relationship.fear",
        "canonical_path": "/custom/穗秋生/害怕值/0",
    }])
    operation = {"op": "increment", "path": "/relationship/affection", "value": 1}
    alias_result = normalize_alias_operations([operation], schema, registry)
    assert alias_result.operations == [operation]
    assert alias_result.events == []


def test_alias_api_is_scoped_to_character_and_refreshes_profile(test_db):
    card = {
        "name": "别名测试卡",
        "scenario": "测试",
        "first_mes": "开始",
        "character_book": {
            "entries": [{
                "comment": "变量规则",
                "enabled": True,
                "content": "<UpdateVariable> 变量更新：好感度每轮最多变化 2 点",
            }]
        },
        "extensions": {
            "tavern_helper": {
                "variables": {
                    "别名测试卡": {
                        "$meta": {"extensible": False, "required": ["好感度"]},
                        "好感度": [5, "[0-100]好感度"],
                    }
                }
            }
        },
    }
    profile = analyze_card(card)
    card["ai_tavern_runtime"] = profile
    first = Character(
        name="别名测试卡",
        description="",
        personality="",
        scenario="测试",
        first_message="开始",
        normalized_json=json.dumps(card, ensure_ascii=False),
        raw_json="{}",
        avatar_path="",
    )
    second = Character(
        name="另一张卡",
        description="",
        personality="",
        scenario="",
        first_message="开始",
        normalized_json=json.dumps({"name": "另一张卡", "first_mes": "开始"}, ensure_ascii=False),
        raw_json="{}",
        avatar_path="",
    )
    test_db.add_all([first, second])
    test_db.commit()

    client = _client(test_db)
    before = client.get(f"/api/characters/{first.id}/state-aliases")
    assert before.status_code == 200
    assert before.json()["confirmed"] == []

    response = client.post(
        f"/api/characters/{first.id}/state-aliases",
        json={"alias": "favor", "semantic": "relationship.affection"},
    )
    assert response.status_code == 200, response.text
    registry = response.json()
    assert registry["summary"]["confirmed_count"] == 1
    assert registry["confirmed"][0]["canonical_path"].endswith("/好感度/0")

    other = client.get(f"/api/characters/{second.id}/state-aliases").json()
    assert other["confirmed"] == []

    runtime_profile = client.get(f"/api/characters/{first.id}/runtime-profile").json()
    assert runtime_profile["version"] == 8
    assert runtime_profile["compatibility_core"] == "tavern-safe-v6"
    assert runtime_profile["state_aliases"]["summary"]["confirmed_count"] == 1

    row = test_db.query(CharacterStateAlias).filter(CharacterStateAlias.character_id == first.id).one()
    deleted = client.delete(f"/api/characters/{first.id}/state-aliases/{row.id}")
    assert deleted.status_code == 200
    assert deleted.json()["confirmed"] == []


def test_decision_trace_records_alias_before_policy_and_schema():
    from app.services.runtime.decision_trace import build_decision_trace

    state, schema = _state_and_schema()
    raw = {"op": "increment", "path": "/custom/穗秋生/favor/0", "value": 1}
    canonical = {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 1}
    state_after = json.loads(json.dumps(state, ensure_ascii=False))
    state_after["custom"]["穗秋生"]["好感度"][0] = 6
    state_after["relationship"]["affection"] = 6

    trace = build_decision_trace(
        source="primary",
        raw_operations=[raw],
        alias_operations=[canonical],
        alias_events=[{
            "operation": raw,
            "applied_as": canonical,
            "decision": "confirmed",
            "reason_code": "ALIAS_CONFIRMED",
            "reason": "当前角色卡已确认别名 favor",
            "alias": "favor",
            "alias_key": "favor",
            "semantic": "relationship.affection",
            "canonical_path": canonical["path"],
            "source": "user_confirmed",
        }],
        policy_operations=[canonical],
        adjusted=[],
        schema_adjusted=[],
        policy_rejected=[],
        applied=[canonical],
        engine_rejected=[],
        state_before=state,
        state_after=state_after,
        state_schema=schema,
    )

    assert trace[0]["alias"]["reason_code"] == "ALIAS_CONFIRMED"
    assert trace[0]["policy"]["reason_code"] == "POLICY_PASSED"
    assert trace[0]["schema"]["reason_code"] == "SCHEMA_PASSED"
    assert trace[0]["apply"]["changed"] is True
    assert trace[0]["normalized_operation"]["path"] == canonical["path"]
