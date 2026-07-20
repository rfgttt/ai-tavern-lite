from __future__ import annotations

import json


def schema_card() -> dict:
    return {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "name": "穗秋生",
        "scenario": "家中",
        "extensions": {},
        "character_book": {
            "entries": [
                {
                    "comment": "[InitVar]",
                    "enabled": False,
                    "content": json.dumps({
                        "$meta": {"extensible": False, "strictSet": True},
                        "世界信息": {
                            "$meta": {"extensible": False, "required": ["日期", "时间", "地点"]},
                            "日期": ["2024年11月9日", "当前日期"],
                            "时间": ["15:30", "当前时间"],
                            "地点": ["家中", "当前地点"],
                        },
                        "穗秋生": {
                            "$meta": {
                                "extensible": False,
                                "required": ["好感度", "害怕值", "依赖值", "重要记忆"],
                            },
                            "好感度": [5, "[0-100]爱意程度"],
                            "害怕值": [95, "[0-100]恐惧程度"],
                            "依赖值": [100, "[0-100]依赖程度"],
                            "重要记忆": [["$__META_EXTENSIBLE__$"], "重要事件列表"],
                        },
                    }, ensure_ascii=False),
                },
                {
                    "comment": "变量规则",
                    "enabled": True,
                    "content": "好感度每轮最多变化2点，一天最多变化5点。<UpdateVariable>_.add('穗秋生.好感度[0]', 1)</UpdateVariable>",
                },
            ]
        },
    }


def test_profile_builds_formal_schema_from_runtime_and_card_declarations():
    from app.services.runtime.card_profile import analyze_card

    profile = analyze_card(schema_card())
    schema = profile["state_schema"]
    affection = schema["fields"]["/custom/穗秋生/好感度/0"]

    assert profile["version"] == 8
    assert profile["capabilities"]["formal_state_schema"] is True
    assert schema["schema"] == "ai-tavern-state-schema/1"
    assert affection["type"] == "integer"
    assert affection["minimum"] == 0
    assert affection["maximum"] == 100
    assert affection["semantic"] == "relationship.affection"
    assert "increment" in affection["update_modes"]
    assert schema["containers"]["/custom/穗秋生"]["extensible"] is False
    assert schema["summary"]["constrained_count"] >= 3


def test_schema_enforces_type_read_only_and_strict_custom_paths_while_clamping_bounds():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.state_engine import apply_patch, build_initial_state

    normalized = schema_card()
    profile = analyze_card(normalized)
    state = build_initial_state(profile, normalized)
    schema = profile["state_schema"]

    result = apply_patch(state, [
        {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 500},
        {"op": "replace", "path": "/custom/穗秋生/害怕值/0", "value": "很害怕"},
        {"op": "add", "path": "/custom/穗秋生/临时字段", "value": 1},
        {"op": "replace", "path": "/character/name", "value": "另一个人"},
    ], schema=schema)

    assert result.state["custom"]["穗秋生"]["好感度"][0] == 100
    assert len(result.applied) == 1
    assert len(result.rejected) == 3
    messages = "\n".join(item["error"] for item in result.rejected)
    assert "类型不匹配" in messages
    assert "未声明该字段" in messages
    assert "只读" in messages


def test_generic_custom_container_remains_extensible_for_compatibility():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.state_engine import apply_patch, build_initial_state

    normalized = {"name": "普通角色", "scenario": "海边", "extensions": {}}
    profile = analyze_card(normalized)
    state = build_initial_state(profile, normalized)

    result = apply_patch(state, [
        {"op": "add", "path": "/custom/clue", "value": "潮湿的信件"},
    ], schema=profile["state_schema"])

    assert result.rejected == []
    assert result.state["custom"]["clue"] == "潮湿的信件"


def test_existing_dynamic_fields_are_reconciled_without_becoming_card_declared():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.state_engine import apply_patch, build_initial_state
    from app.services.runtime.state_schema import reconcile_state_schema, validate_state_against_schema

    normalized = {"name": "普通角色", "extensions": {}}
    profile = analyze_card(normalized)
    state = build_initial_state(profile, normalized)
    state["custom"]["legacy"] = 3
    reconciled = reconcile_state_schema(profile["state_schema"], state)

    field = reconciled["fields"]["/custom/legacy"]
    assert field["declared"] is False
    assert field["source"] == "runtime_dynamic"
    result = apply_patch(state, [
        {"op": "increment", "path": "/custom/legacy", "value": 2},
    ], schema=reconciled)
    assert result.state["custom"]["legacy"] == 5
    validation = validate_state_against_schema(result.state, reconciled)
    assert validation["valid"] is True
    assert validation["warning_count"] >= 1


def test_manual_state_validation_reports_required_type_and_bounds():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.state_engine import build_initial_state
    from app.services.runtime.state_schema import validate_state_against_schema

    normalized = schema_card()
    profile = analyze_card(normalized)
    state = build_initial_state(profile, normalized)
    state["custom"]["穗秋生"]["好感度"][0] = "错误类型"
    del state["custom"]["世界信息"]["地点"]

    validation = validate_state_against_schema(state, profile["state_schema"])
    assert validation["valid"] is False
    codes = {item["code"] for item in validation["errors"]}
    assert "TYPE_MISMATCH" in codes
    assert "REQUIRED_FIELD_MISSING" in codes


def test_prompt_contains_compact_schema_contract():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.prompt import build_runtime_prompt
    from app.services.runtime.state_engine import build_initial_state

    normalized = schema_card()
    profile = analyze_card(normalized)
    state = build_initial_state(profile, normalized)
    prompt = build_runtime_prompt(profile, state)

    assert "Formal State Schema" in prompt
    assert "/custom/穗秋生/好感度/0" in prompt
    assert "/relationship/affection" not in prompt
    assert "range=0..100" in prompt


def test_decision_trace_includes_schema_metadata():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.decision_trace import build_decision_trace
    from app.services.runtime.state_engine import apply_patch, build_initial_state

    normalized = schema_card()
    profile = analyze_card(normalized)
    before = build_initial_state(profile, normalized)
    operation = {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 1}
    after = apply_patch(before, [operation], schema=profile["state_schema"]).state
    trace = build_decision_trace(
        source="primary",
        raw_operations=[operation],
        policy_operations=[operation],
        adjusted=[],
        policy_rejected=[],
        applied=[operation],
        engine_rejected=[],
        state_before=before,
        state_after=after,
        state_schema=profile["state_schema"],
    )

    field = trace[0]["field"]
    assert field["declared"] is True
    assert field["schema_type"] == "integer"
    assert field["semantic"] == "relationship.affection"
    assert field["minimum"] == 0
    assert field["maximum"] == 100


def test_whole_state_validation_rejects_new_undeclared_field_in_strict_container():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.state_engine import build_initial_state
    from app.services.runtime.state_schema import validate_state_against_schema

    normalized = schema_card()
    profile = analyze_card(normalized)
    state = build_initial_state(profile, normalized)
    state["custom"]["穗秋生"]["临时字段"] = 1

    validation = validate_state_against_schema(state, profile["state_schema"])
    assert validation["valid"] is False
    assert any(item["code"] == "UNDECLARED_FIELD" for item in validation["errors"])


def test_schema_range_adjustment_is_explicit_in_engine_and_decision_trace():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.decision_trace import build_decision_trace
    from app.services.runtime.state_engine import apply_patch, build_initial_state

    normalized = schema_card()
    profile = analyze_card(normalized)
    before = build_initial_state(profile, normalized)
    raw = {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 500}
    result = apply_patch(before, [raw], schema=profile["state_schema"])

    assert result.applied == [{"op": "increment", "path": raw["path"], "value": 95}]
    assert result.adjusted == [{
        "operation": raw,
        "applied_as": {"op": "increment", "path": raw["path"], "value": 95},
        "reason_code": "SCHEMA_RANGE_CLAMPED",
        "reason": "按 Formal State Schema 数值范围调整操作",
    }]

    trace = build_decision_trace(
        source="primary",
        raw_operations=[raw],
        policy_operations=[raw],
        adjusted=[],
        schema_adjusted=result.adjusted,
        policy_rejected=[],
        applied=result.applied,
        engine_rejected=[],
        state_before=before,
        state_after=result.state,
        state_schema=profile["state_schema"],
    )
    item = trace[0]
    assert item["outcome"] == "adjusted_applied"
    assert item["schema"]["decision"] == "adjusted"
    assert item["schema"]["reason_code"] == "SCHEMA_RANGE_CLAMPED"
    assert item["normalized_operation"]["value"] == 95
    assert item["apply"]["before"] == 5
    assert item["apply"]["after"] == 100


def test_schema_rejection_is_separate_from_state_merge_stage():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.decision_trace import build_decision_trace
    from app.services.runtime.state_engine import apply_patch, build_initial_state

    normalized = schema_card()
    profile = analyze_card(normalized)
    before = build_initial_state(profile, normalized)
    raw = {"op": "replace", "path": "/custom/穗秋生/好感度/0", "value": "很多"}
    result = apply_patch(before, [raw], schema=profile["state_schema"])
    trace = build_decision_trace(
        source="primary",
        raw_operations=[raw],
        policy_operations=[raw],
        adjusted=[],
        schema_adjusted=result.adjusted,
        policy_rejected=[],
        applied=result.applied,
        engine_rejected=result.rejected,
        state_before=before,
        state_after=result.state,
        state_schema=profile["state_schema"],
    )

    item = trace[0]
    assert item["outcome"] == "rejected"
    assert item["policy"]["reason_code"] == "POLICY_PASSED"
    assert item["schema"]["decision"] == "rejected"
    assert item["schema"]["reason_code"] == "SCHEMA_TYPE_MISMATCH"
    assert item["apply"]["decision"] == "not_attempted"
    assert item["apply"]["reason_code"] == "NOT_ATTEMPTED_SCHEMA_REJECTED"


def test_projection_alias_is_canonicalized_to_card_owned_relationship_field():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.decision_trace import build_decision_trace
    from app.services.runtime.state_engine import apply_patch, build_initial_state

    normalized = schema_card()
    profile = analyze_card(normalized)
    before = build_initial_state(profile, normalized)
    schema = profile["state_schema"]
    raw = {"op": "increment", "path": "/relationship/affection", "value": 1}

    result = apply_patch(before, [raw], schema=schema)

    canonical = "/custom/穗秋生/好感度/0"
    assert schema["semantic_index"]["relationship.affection"]["canonical_path"] == canonical
    assert schema["fields"]["/relationship/affection"]["semantic_role"] == "projection"
    assert schema["fields"][canonical]["semantic_role"] == "source"
    assert result.rejected == []
    assert result.applied == [{"op": "increment", "path": canonical, "value": 1}]
    assert result.state["custom"]["穗秋生"]["好感度"][0] == 6
    assert result.state["relationship"]["affection"] == 6
    assert result.adjusted[0]["reason_code"] == "SCHEMA_PATH_CANONICALIZED"

    trace = build_decision_trace(
        source="probe",
        raw_operations=[raw],
        policy_operations=[raw],
        adjusted=[],
        schema_adjusted=result.adjusted,
        policy_rejected=[],
        applied=result.applied,
        engine_rejected=result.rejected,
        state_before=before,
        state_after=result.state,
        state_schema=schema,
    )
    item = trace[0]
    assert item["outcome"] == "adjusted_applied"
    assert item["normalized_operation"]["path"] == canonical
    assert item["schema"]["reason_code"] == "SCHEMA_PATH_CANONICALIZED"
    assert item["apply"]["before"] == 5
    assert item["apply"]["after"] == 6
    assert item["apply"]["changed"] is True


def test_projection_alias_can_be_canonicalized_and_range_clamped_in_one_operation():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.decision_trace import build_decision_trace
    from app.services.runtime.state_engine import apply_patch, build_initial_state

    normalized = schema_card()
    profile = analyze_card(normalized)
    before = build_initial_state(profile, normalized)
    schema = profile["state_schema"]
    raw = {"op": "increment", "path": "/relationship/affection", "value": 500}

    result = apply_patch(before, [raw], schema=schema)
    assert result.state["relationship"]["affection"] == 100
    assert result.state["custom"]["穗秋生"]["好感度"][0] == 100
    assert [item["reason_code"] for item in result.adjusted] == [
        "SCHEMA_PATH_CANONICALIZED",
        "SCHEMA_RANGE_CLAMPED",
    ]

    trace = build_decision_trace(
        source="probe",
        raw_operations=[raw],
        policy_operations=[raw],
        adjusted=[],
        schema_adjusted=result.adjusted,
        policy_rejected=[],
        applied=result.applied,
        engine_rejected=result.rejected,
        state_before=before,
        state_after=result.state,
        state_schema=schema,
    )
    item = trace[0]
    assert item["schema"]["reason_code"] == "SCHEMA_MULTIPLE_ADJUSTMENTS"
    assert [part["reason_code"] for part in item["schema"]["adjustments"]] == [
        "SCHEMA_PATH_CANONICALIZED",
        "SCHEMA_RANGE_CLAMPED",
    ]
    assert item["normalized_operation"]["value"] == 95
    assert item["apply"]["changed"] is True


def test_strict_container_probe_reaches_schema_rejection_with_safe_field_name():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.state_engine import apply_patch, build_initial_state

    normalized = schema_card()
    profile = analyze_card(normalized)
    state = build_initial_state(profile, normalized)
    operation = {
        "op": "add",
        "path": "/custom/世界信息/p2_probe_unknown_field",
        "value": 1,
    }

    result = apply_patch(state, [operation], schema=profile["state_schema"])

    assert result.applied == []
    assert result.rejected[0]["operation"] == operation
    assert "状态 Schema 未声明该字段" in result.rejected[0]["error"]
    assert "禁止字段" not in result.rejected[0]["error"]


def test_persisted_turn_uses_canonical_path_and_records_real_state_change(test_db):
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Character, ChatSession, Message, SessionState, TurnSnapshot
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.state_engine import build_initial_state
    from app.services.runtime.turn_finalizer import finalize_stream_turn

    normalized = schema_card()
    character = Character(
        name="穗秋生",
        description="",
        personality="",
        scenario="家中",
        first_message="开始",
        normalized_json=json.dumps(normalized, ensure_ascii=False),
        raw_json=json.dumps(normalized, ensure_ascii=False),
        avatar_path="",
    )
    test_db.add(character)
    test_db.flush()
    session = ChatSession(character_id=character.id, title="P2.1 持久化测试")
    test_db.add(session)
    test_db.flush()
    message = Message(
        session_id=session.id,
        role="assistant",
        content="",
        sequence=0,
        generation_status="generating",
    )
    test_db.add(message)

    profile = analyze_card(normalized)
    before = build_initial_state(profile, normalized)
    test_db.add(SessionState(
        session_id=session.id,
        profile_json=json.dumps(profile, ensure_ascii=False),
        initial_state_json=json.dumps(before, ensure_ascii=False),
        state_json=json.dumps(before, ensure_ascii=False),
        revision=0,
    ))
    test_db.commit()

    factory = sessionmaker(bind=test_db.get_bind(), autocommit=False, autoflush=False)
    raw = {"op": "increment", "path": "/relationship/affection", "value": 1}
    payload = finalize_stream_turn(
        factory,
        session_id=session.id,
        message_id=message.id,
        final_status="complete",
        visible_content="她稍微放松了一些。",
        state_before=before,
        operations=[raw],
        events=[],
        choices=[],
        dice=[],
        battle_checks=[],
        battle=None,
        expression="",
        triggered_lorebook=[],
        parser_errors=[],
        state_update_source="p2_1_test",
    )

    assert payload["patch_applied"] is True
    assert payload["state_changed"] is True
    assert payload["state"]["relationship"]["affection"] == 6
    assert payload["state"]["custom"]["穗秋生"]["好感度"][0] == 6

    snapshot = test_db.query(TurnSnapshot).filter(TurnSnapshot.message_id == message.id).one()
    patch = json.loads(snapshot.patch_json)
    trace = json.loads(snapshot.decision_trace_json)
    assert patch == [{"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 1}]
    assert trace[0]["normalized_operation"]["path"] == "/custom/穗秋生/好感度/0"
    assert trace[0]["schema"]["reason_code"] == "SCHEMA_PATH_CANONICALIZED"
    assert trace[0]["apply"]["before"] == 5
    assert trace[0]["apply"]["after"] == 6
    assert trace[0]["apply"]["changed"] is True


def test_projection_alias_removal_is_checked_against_canonical_required_field():
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.decision_trace import build_decision_trace
    from app.services.runtime.state_engine import apply_patch, build_initial_state

    normalized = schema_card()
    profile = analyze_card(normalized)
    before = build_initial_state(profile, normalized)
    schema = profile["state_schema"]
    raw = {"op": "remove", "path": "/relationship/affection"}

    result = apply_patch(before, [raw], schema=schema)
    trace = build_decision_trace(
        source="probe",
        raw_operations=[raw],
        policy_operations=[raw],
        adjusted=[],
        schema_adjusted=result.adjusted,
        policy_rejected=[],
        applied=result.applied,
        engine_rejected=result.rejected,
        state_before=before,
        state_after=result.state,
        state_schema=schema,
    )

    assert result.applied == []
    assert "Schema 要求该字段必须存在" in result.rejected[0]["error"]
    assert trace[0]["normalized_operation"]["path"] == "/custom/穗秋生/好感度/0"
    assert trace[0]["schema"]["reason_code"] == "SCHEMA_REQUIRED_FIELD"
    assert trace[0]["apply"]["reason_code"] == "NOT_ATTEMPTED_SCHEMA_REJECTED"
