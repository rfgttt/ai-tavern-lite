from __future__ import annotations

import json
from types import SimpleNamespace


def card_normalized() -> dict:
    return {
        "name": "穗秋生",
        "extensions": {},
        "character_book": {
            "entries": [
                {
                    "comment": "[InitVar]",
                    "enabled": False,
                    "content": json.dumps({
                        "世界信息": {
                            "日期": ["2024年11月9日", "当前日期"],
                            "时间": ["15:30", "当前时间"],
                            "地点": ["家中", "当前地点"],
                        },
                        "穗秋生": {
                            "好感度": [5, "[0-100]爱意程度"],
                            "害怕值": [95, "[0-100]恐惧程度"],
                            "依赖值": [100, "[0-100]依赖程度"],
                            "重要记忆": [["$__META_EXTENSIBLE__$"], "重要事件"],
                        },
                    }, ensure_ascii=False),
                },
                {
                    "comment": "变量规则",
                    "enabled": True,
                    "content": """
好感度每轮最多变化2点，一天最多变化5点。
害怕值每轮最多变化2点，一天最多变化5点。
依赖值每轮最多变化2点，一天最多变化5点。
最终阶段锁定：当好感度100且害怕值0且依赖值100时，三个数值完全锁定。
<UpdateVariable>_.add('穗秋生.好感度[0]', 1)</UpdateVariable>
""".strip(),
                },
                {
                    "comment": "控制器",
                    "enabled": True,
                    "content": """
const affection = getvar('stat_data.穗秋生.好感度[0]');
if (affection === 100) { getwi(null, '性格锚定_阶段06'); }
else if (affection >= 81) { getwi(null, '性格锚定_阶段05'); }
else if (affection >= 61) { getwi(null, '性格锚定_阶段04'); }
else if (affection >= 41) { getwi(null, '性格锚定_阶段03'); }
else if (affection >= 21) { getwi(null, '性格锚定_阶段02'); }
else { getwi(null, '性格锚定_基础阶段'); }
""".strip(),
                },
            ]
        },
    }


def initial_state():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.state_engine import build_initial_state

    normalized = card_normalized()
    profile = analyze_card(normalized)
    return profile, build_initial_state(profile, normalized)


def test_extracts_limits_paths_lock_stage_and_context_recommendation():
    from app.services.runtime.card_profile import analyze_card

    profile = analyze_card(card_normalized())
    policy = profile["state_policy"]

    assert policy["per_turn_absolute_limit"] == 2
    assert policy["per_day_absolute_limit"] == 5
    assert policy["terminal_lock"]["enabled"] is True
    assert "/custom/穗秋生/好感度/0" in policy["relationship_paths"]["affection"]
    assert profile["recommended_context_window"] >= 8192


def test_initial_stage_is_projected_from_card_controller():
    _profile, state = initial_state()
    assert state["relationship"]["stage"] == "基础阶段 · 极度恐惧"


def test_enforces_per_turn_limit_bounds_and_noop_filter():
    from app.services.runtime.state_policy import enforce_state_policy

    profile, state = initial_state()
    result = enforce_state_policy(state, [
        {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 8},
        {"op": "increment", "path": "/custom/穗秋生/害怕值/0", "value": -9},
        {"op": "increment", "path": "/custom/穗秋生/依赖值/0", "value": 1},
        {"op": "replace", "path": "/custom/世界信息/地点/0", "value": "家中"},
    ], profile["state_policy"])

    assert result.operations[0]["value"] == 2
    assert result.operations[1]["value"] == -2
    assert all(item.get("path") != "/custom/穗秋生/依赖值/0" for item in result.operations)
    assert len(result.adjusted) == 2
    assert any("边界" in item["error"] for item in result.rejected)
    assert any("相同" in item["error"] for item in result.rejected)


def test_enforces_daily_absolute_limit_from_previous_snapshots():
    from app.services.runtime.state_policy import enforce_state_policy
    from app.services.runtime.state_engine import apply_patch

    profile, state = initial_state()
    after_one = apply_patch(state, [
        {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 2},
    ]).state
    after_two = apply_patch(after_one, [
        {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 2},
    ]).state
    snapshots = [
        SimpleNamespace(
            state_before_json=json.dumps(state, ensure_ascii=False),
            state_after_json=json.dumps(after_one, ensure_ascii=False),
        ),
        SimpleNamespace(
            state_before_json=json.dumps(after_one, ensure_ascii=False),
            state_after_json=json.dumps(after_two, ensure_ascii=False),
        ),
    ]

    result = enforce_state_policy(after_two, [
        {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 2},
    ], profile["state_policy"], snapshots)

    assert result.operations == [
        {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 1}
    ]
    assert result.adjusted


def test_terminal_lock_rejects_all_three_relationship_changes():
    from app.services.runtime.state_policy import enforce_state_policy, apply_stage_projection
    from app.services.runtime.state_engine import apply_patch

    profile, state = initial_state()
    terminal = apply_patch(state, [
        {"op": "replace", "path": "/custom/穗秋生/好感度/0", "value": 100},
        {"op": "replace", "path": "/custom/穗秋生/害怕值/0", "value": 0},
    ]).state
    terminal = apply_stage_projection(terminal, profile["state_policy"])
    result = enforce_state_policy(terminal, [
        {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": -2},
        {"op": "increment", "path": "/custom/穗秋生/害怕值/0", "value": 2},
        {"op": "increment", "path": "/custom/穗秋生/依赖值/0", "value": -2},
    ], profile["state_policy"])

    assert result.operations == []
    assert len(result.rejected) == 3
    assert terminal["relationship"]["stage"] == "阶段06 · 圆满"



def test_terminal_lock_activates_immediately_after_reaching_terminal_in_same_turn():
    from app.services.runtime.state_policy import enforce_state_policy
    from app.services.runtime.state_engine import apply_patch

    profile, state = initial_state()
    state = apply_patch(state, [
        {"op": "replace", "path": "/custom/穗秋生/好感度/0", "value": 99},
        {"op": "replace", "path": "/custom/穗秋生/害怕值/0", "value": 1},
    ]).state
    result = enforce_state_policy(state, [
        {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 1},
        {"op": "increment", "path": "/custom/穗秋生/害怕值/0", "value": -1},
        {"op": "increment", "path": "/custom/穗秋生/依赖值/0", "value": -1},
    ], profile["state_policy"])

    assert len(result.operations) == 2
    assert result.operations[-1]["path"] == "/custom/穗秋生/害怕值/0"
    assert len(result.rejected) == 1
    assert "终局状态已锁定" in result.rejected[0]["error"]

def test_duplicate_important_memory_is_not_appended_twice():
    from app.services.runtime.state_policy import enforce_state_policy
    from app.services.runtime.state_engine import apply_patch

    profile, state = initial_state()
    state = apply_patch(state, [
        {"op": "append", "path": "/custom/穗秋生/重要记忆/0", "value": "第一次去医院"},
    ]).state
    result = enforce_state_policy(state, [
        {"op": "append", "path": "/custom/穗秋生/重要记忆/0", "value": "第一次去医院"},
    ], profile["state_policy"])

    assert result.operations == []
    assert "重复" in result.rejected[0]["error"]


def test_turn_finalizer_applies_policy_to_primary_or_fallback_operations(test_db):
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Character, ChatSession, Message, SessionState, TurnSnapshot
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.state_engine import build_initial_state
    from app.services.runtime.turn_finalizer import finalize_stream_turn

    normalized = card_normalized()
    profile = analyze_card(normalized)
    state = build_initial_state(profile, normalized)
    character = Character(
        name='穗秋生',
        normalized_json=json.dumps(normalized, ensure_ascii=False),
        raw_json='{}',
    )
    test_db.add(character)
    test_db.flush()
    session = ChatSession(character_id=character.id, title='规则测试')
    test_db.add(session)
    test_db.flush()
    message = Message(session_id=session.id, role='assistant', content='', sequence=0, generation_status='generating')
    test_db.add(message)
    test_db.flush()
    test_db.add(SessionState(
        session_id=session.id,
        profile_json=json.dumps(profile, ensure_ascii=False),
        initial_state_json=json.dumps(state, ensure_ascii=False),
        state_json=json.dumps(state, ensure_ascii=False),
        revision=0,
    ))
    test_db.commit()

    factory = sessionmaker(autocommit=False, autoflush=False, bind=test_db.get_bind())
    payload = finalize_stream_turn(
        factory,
        session_id=session.id,
        message_id=message.id,
        final_status='complete',
        visible_content='剧情回复',
        state_before=state,
        operations=[
            {'op': 'increment', 'path': '/custom/穗秋生/好感度/0', 'value': 9},
            {'op': 'increment', 'path': '/custom/穗秋生/害怕值/0', 'value': -9},
        ],
        events=[], choices=[], dice=[], battle_checks=[], battle=None, expression='',
        triggered_lorebook=[], parser_errors=[], state_update_source='primary_response',
    )

    assert payload['state']['relationship']['affection'] == 7
    assert payload['state']['relationship']['fear'] == 93
    assert payload['state']['relationship']['stage'] == '基础阶段 · 极度恐惧'
    assert payload['patch_applied'] is True
    snapshot = test_db.query(TurnSnapshot).filter(TurnSnapshot.message_id == message.id).first()
    assert snapshot is not None
    patch = json.loads(snapshot.patch_json)
    assert patch[0]['value'] == 2
    assert patch[1]['value'] == -2
    assert '状态规则调整' in snapshot.events_json
