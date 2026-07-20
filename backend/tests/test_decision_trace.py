from app.services.runtime.decision_trace import build_decision_trace


def _trace(**overrides):
    values = {
        "source": "fallback",
        "raw_operations": [],
        "policy_operations": [],
        "adjusted": [],
        "policy_rejected": [],
        "applied": [],
        "engine_rejected": [],
        "state_before": {},
        "state_after": {},
    }
    values.update(overrides)
    return build_decision_trace(**values)


def test_applied_operation_never_uses_rejection_reason_code():
    raw = {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 1}
    trace = _trace(
        raw_operations=[raw],
        policy_operations=[raw],
        applied=[raw],
        state_before={"custom": {"穗秋生": {"好感度": [7, "说明"]}}},
        state_after={"custom": {"穗秋生": {"好感度": [8, "说明"]}}},
    )

    item = trace[0]
    assert item["outcome"] == "applied"
    assert item["policy"]["decision"] == "passed"
    assert item["policy"]["reason_code"] == "POLICY_PASSED"
    assert item["apply"]["decision"] == "applied"
    assert item["apply"]["reason_code"] == "APPLIED"
    assert item["apply"]["before"] == 7
    assert item["apply"]["after"] == 8
    assert "REJECTED" not in item["apply"]["reason_code"]


def test_adjusted_operation_reports_adjusted_applied_with_separate_stages():
    raw = {"op": "increment", "path": "/relationship/affection", "value": 5}
    adjusted = {"op": "increment", "path": "/relationship/affection", "value": 2}
    trace = _trace(
        raw_operations=[raw],
        policy_operations=[adjusted],
        adjusted=[{
            "operation": raw,
            "applied_as": adjusted,
            "reason": "按角色卡声明的每轮/每日关系变化上限调整",
        }],
        applied=[adjusted],
        state_before={"relationship": {"affection": 5}},
        state_after={"relationship": {"affection": 7}},
    )

    item = trace[0]
    assert item["outcome"] == "adjusted_applied"
    assert item["policy"]["decision"] == "adjusted"
    assert item["policy"]["reason_code"] == "RELATION_DELTA_LIMIT"
    assert item["apply"]["decision"] == "applied"
    assert item["apply"]["reason_code"] == "APPLIED"
    assert item["normalized_operation"] == adjusted


def test_policy_rejection_is_not_attempted_by_state_engine():
    raw = {"op": "replace", "path": "/custom/世界信息/时间/0", "value": "16:00"}
    state = {"custom": {"世界信息": {"时间": ["16:00", "当前时间"]}}}
    trace = _trace(
        raw_operations=[raw],
        policy_rejected=[{"operation": raw, "error": "替换值与当前状态相同，已忽略无效操作"}],
        state_before=state,
        state_after=state,
    )

    item = trace[0]
    assert item["outcome"] == "rejected"
    assert item["policy"]["decision"] == "rejected"
    assert item["policy"]["reason_code"] == "NO_STATE_CHANGE"
    assert item["apply"]["decision"] == "not_attempted"
    assert item["apply"]["reason_code"] == "NOT_ATTEMPTED_POLICY_REJECTED"
    assert item["apply"]["changed"] is False


def test_engine_rejection_keeps_policy_passed_and_engine_reason():
    raw = {"op": "replace", "path": "/missing", "value": 1}
    trace = _trace(
        raw_operations=[raw],
        policy_operations=[raw],
        engine_rejected=[{"operation": raw, "error": "路径不存在"}],
    )

    item = trace[0]
    assert item["outcome"] == "rejected"
    assert item["policy"]["reason_code"] == "POLICY_PASSED"
    assert item["apply"]["decision"] == "rejected"
    assert item["apply"]["reason_code"] == "PATH_NOT_FOUND"


def test_existing_custom_path_is_not_classified_as_unknown():
    raw = {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 1}
    trace = _trace(
        raw_operations=[raw],
        policy_operations=[raw],
        applied=[raw],
        state_before={"custom": {"穗秋生": {"好感度": [7, "说明"]}}},
        state_after={"custom": {"穗秋生": {"好感度": [8, "说明"]}}},
    )

    assert trace[0]["field"] == {
        "path": "/custom/穗秋生/好感度/0",
        "namespace": "custom",
        "classification": "existing",
        "existed_before": True,
        "exists_after": True,
    }


def test_new_path_is_classified_as_created():
    raw = {"op": "increment", "path": "/custom/new_counter", "value": 1}
    trace = _trace(
        raw_operations=[raw],
        policy_operations=[raw],
        applied=[raw],
        state_before={"custom": {}},
        state_after={"custom": {"new_counter": 1}},
    )

    assert trace[0]["field"]["classification"] == "created"
    assert trace[0]["field"]["existed_before"] is False
    assert trace[0]["field"]["exists_after"] is True


def test_duplicate_raw_operations_are_matched_one_by_one():
    raw = {"op": "increment", "path": "/custom/counter", "value": 1}
    trace = _trace(
        raw_operations=[raw, raw],
        policy_operations=[raw],
        policy_rejected=[{"operation": raw, "error": "关系数值已达到边界或当日变化上限，操作未生效"}],
        applied=[raw],
        state_before={"custom": {"counter": 0}},
        state_after={"custom": {"counter": 1}},
    )

    assert [item["outcome"] for item in trace] == ["applied", "rejected"]


def test_defensive_trace_never_marks_unchanged_result_as_applied():
    raw = {"op": "increment", "path": "/relationship/affection", "value": 1}
    state = {"relationship": {"affection": 73}}
    trace = _trace(
        raw_operations=[raw],
        policy_operations=[raw],
        applied=[raw],
        state_before=state,
        state_after=state,
    )

    item = trace[0]
    assert item["outcome"] == "not_applied"
    assert item["apply"]["decision"] == "not_applied"
    assert item["apply"]["reason_code"] == "NO_STATE_CHANGE_AFTER_PROJECTION"
    assert item["apply"]["changed"] is False
