from __future__ import annotations

import copy
from typing import Any

from .state_schema import resolve_schema_field


def _reason_code(message: str, *, stage: str) -> str:
    text = str(message or "")
    rules = (
        ("终局状态", "TERMINAL_STATE_LOCKED"),
        ("每轮/每日", "RELATION_DELTA_LIMIT"),
        ("当日变化上限", "RELATION_DELTA_LIMIT"),
        ("状态 Schema 数值已达到边界", "SCHEMA_VALUE_BOUNDARY"),
        ("按 Formal State Schema 数值范围调整", "SCHEMA_RANGE_CLAMPED"),
        ("达到边界", "VALUE_BOUNDARY"),
        ("边界", "VALUE_BOUNDARY"),
        ("相同", "NO_STATE_CHANGE"),
        ("重复", "DUPLICATE_VALUE"),
        ("路径不存在", "PATH_NOT_FOUND"),
        ("索引越界", "INDEX_OUT_OF_RANGE"),
        ("必须是数字", "TYPE_MISMATCH"),
        ("必须是数组", "TYPE_MISMATCH"),
        ("必须是对象", "TYPE_MISMATCH"),
        ("不支持的操作", "UNSUPPORTED_OPERATION"),
        ("禁止字段", "FORBIDDEN_PATH"),
        ("状态 Schema 未声明", "SCHEMA_PATH_UNDECLARED"),
        ("Schema 类型不匹配", "SCHEMA_TYPE_MISMATCH"),
        ("Schema 数组元素类型不匹配", "SCHEMA_TYPE_MISMATCH"),
        ("Schema 不允许", "SCHEMA_OPERATION_NOT_ALLOWED"),
        ("Schema 将该字段声明为只读", "SCHEMA_READ_ONLY"),
        ("Schema 要求该字段必须存在", "SCHEMA_REQUIRED_FIELD"),
        ("Schema 禁止修改声明元数据", "SCHEMA_METADATA_READ_ONLY"),
        ("状态大小超过限制", "STATE_SIZE_LIMIT"),
    )
    for token, code in rules:
        if token in text:
            return code
    if not text:
        return "UNKNOWN"
    return "POLICY_REJECTED" if stage == "policy" else "STATE_ENGINE_REJECTED"


def _lookup(state: Any, path: Any) -> tuple[bool, Any]:
    if not isinstance(path, str) or not path.startswith("/"):
        return False, None
    current = state
    try:
        for raw in path[1:].split("/") if path != "/" else [""]:
            part = raw.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict):
                current = current[part]
            elif isinstance(current, list):
                current = current[int(part)]
            else:
                return False, None
        return True, copy.deepcopy(current)
    except (KeyError, IndexError, TypeError, ValueError):
        return False, None


def _same_operation(left: Any, right: Any) -> bool:
    return isinstance(left, dict) and isinstance(right, dict) and left == right


def _take_match(items: list[Any], operation: Any, *, nested_key: str | None = None) -> Any | None:
    for index, item in enumerate(items):
        candidate = item.get(nested_key) if nested_key and isinstance(item, dict) else item
        if _same_operation(candidate, operation):
            return items.pop(index)
    return None


def _take_adjustment_chain(items: list[Any], operation: Any) -> tuple[list[dict[str, Any]], Any]:
    chain: list[dict[str, Any]] = []
    effective = copy.deepcopy(operation)
    for _ in range(8):
        match = _take_match(items, effective, nested_key="operation")
        if not isinstance(match, dict):
            break
        chain.append(match)
        next_operation = match.get("applied_as")
        if not isinstance(next_operation, dict) or next_operation == effective:
            break
        effective = copy.deepcopy(next_operation)
    return chain, effective


def _field_metadata(
    path: Any,
    state_before: dict[str, Any],
    state_after: dict[str, Any],
    state_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_path = path if isinstance(path, str) else ""
    before_exists, _ = _lookup(state_before, normalized_path)
    after_exists, _ = _lookup(state_after, normalized_path)
    if before_exists:
        classification = "existing"
    elif after_exists:
        classification = "created"
    else:
        classification = "unresolved"
    namespace = ""
    if normalized_path.startswith("/"):
        namespace = normalized_path[1:].split("/", 1)[0].replace("~1", "/").replace("~0", "~")
    result = {
        "path": normalized_path,
        "namespace": namespace,
        "classification": classification,
        "existed_before": before_exists,
        "exists_after": after_exists,
    }
    schema_field, array_item = resolve_schema_field(state_schema, normalized_path)
    if schema_field:
        result.update({
            "declared": bool(schema_field.get("declared")),
            "schema_type": schema_field.get("items_type") if array_item else schema_field.get("type"),
            "semantic": schema_field.get("semantic", ""),
            "schema_source": schema_field.get("source", ""),
            "mutable": bool(schema_field.get("mutable", True)),
            "update_modes": schema_field.get("update_modes", []),
            "canonical_path": schema_field.get("canonical_path", normalized_path),
            "semantic_role": schema_field.get("semantic_role", "source"),
            "derived": bool(schema_field.get("derived", False)),
        })
        if "minimum" in schema_field:
            result["minimum"] = schema_field.get("minimum")
        if "maximum" in schema_field:
            result["maximum"] = schema_field.get("maximum")
    elif isinstance(state_schema, dict) and state_schema.get("schema"):
        result["declared"] = False
    return result


def build_decision_trace(
    *,
    source: str,
    raw_operations: list[dict[str, Any]],
    policy_operations: list[dict[str, Any]],
    adjusted: list[dict[str, Any]],
    schema_adjusted: list[dict[str, Any]] | None = None,
    policy_rejected: list[dict[str, Any]],
    applied: list[dict[str, Any]],
    engine_rejected: list[dict[str, Any]],
    state_before: dict[str, Any],
    state_after: dict[str, Any],
    state_schema: dict[str, Any] | None = None,
    alias_operations: list[dict[str, Any]] | None = None,
    alias_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build a consistent, stage-aware explanation for every state operation.

    The trace separates policy decisions from state-engine decisions. An applied
    operation can therefore never carry a rejection code, and policy rejections
    are always marked as not attempted by the state engine.
    """

    raw_list = copy.deepcopy(raw_operations if isinstance(raw_operations, list) else [])
    alias_stage_enabled = alias_operations is not None or alias_events is not None
    remaining_alias_operations = copy.deepcopy(alias_operations if isinstance(alias_operations, list) else raw_list)
    remaining_alias_events = copy.deepcopy(alias_events if isinstance(alias_events, list) else [])
    remaining_policy_operations = copy.deepcopy(policy_operations if isinstance(policy_operations, list) else [])
    remaining_adjustments = copy.deepcopy(adjusted if isinstance(adjusted, list) else [])
    remaining_schema_adjustments = copy.deepcopy(schema_adjusted if isinstance(schema_adjusted, list) else [])
    remaining_policy_rejections = copy.deepcopy(policy_rejected if isinstance(policy_rejected, list) else [])
    remaining_applied = copy.deepcopy(applied if isinstance(applied, list) else [])
    remaining_engine_rejections = copy.deepcopy(engine_rejected if isinstance(engine_rejected, list) else [])
    entries: list[dict[str, Any]] = []

    for index, raw in enumerate(raw_list, start=1):
        operation_id = f"op-{index:03d}"
        if not isinstance(raw, dict):
            entries.append({
                "operation_id": operation_id,
                "source": source or "unknown",
                "outcome": "rejected",
                "raw_operation": copy.deepcopy(raw),
                "normalized_operation": copy.deepcopy(raw),
                "field": _field_metadata(None, state_before, state_after, state_schema),
                **({"alias": {
                    "decision": "not_attempted",
                    "reason_code": "NOT_ATTEMPTED_INVALID_OPERATION",
                    "reason": "状态操作格式无效，未进入角色卡别名解析",
                }} if alias_stage_enabled else {}),
                "policy": {
                    "decision": "rejected",
                    "reason_code": "INVALID_OPERATION_SHAPE",
                    "reason": "状态操作必须是对象",
                },
                **({"schema": {
                    "decision": "not_attempted",
                    "reason_code": "NOT_ATTEMPTED_POLICY_REJECTED",
                    "reason": "状态规则已拒绝该操作，未进入 Formal State Schema 校验",
                }} if state_schema else {}),
                "apply": {
                    "decision": "not_attempted",
                    "reason_code": "NOT_ATTEMPTED_POLICY_REJECTED",
                    "reason": "状态规则已拒绝该操作，未进入状态引擎",
                    "changed": False,
                },
            })
            continue

        alias_event = _take_match(remaining_alias_events, raw, nested_key="operation")
        alias_effective = (
            copy.deepcopy(alias_event.get("applied_as"))
            if isinstance(alias_event, dict) and isinstance(alias_event.get("applied_as"), dict)
            else copy.deepcopy(raw)
        )
        _take_match(remaining_alias_operations, alias_effective)
        if isinstance(alias_event, dict):
            alias_decision = str(alias_event.get("decision") or "suggested")
            alias_result = {
                "decision": alias_decision,
                "reason_code": str(alias_event.get("reason_code") or "ALIAS_CONFIRMATION_REQUIRED"),
                "reason": str(alias_event.get("reason") or "角色卡字段别名需要确认"),
                "alias": alias_event.get("alias", ""),
                "alias_key": alias_event.get("alias_key", ""),
                "semantic": alias_event.get("semantic", ""),
                "canonical_path": alias_event.get("canonical_path", ""),
                "source": alias_event.get("source", ""),
                "candidates": copy.deepcopy(alias_event.get("candidates", [])),
            }
            if alias_effective != raw:
                alias_result["input_operation"] = copy.deepcopy(raw)
                alias_result["output_operation"] = copy.deepcopy(alias_effective)
        else:
            raw_path = raw.get("path") if isinstance(raw, dict) else None
            schema_field, _ = resolve_schema_field(state_schema, raw_path)
            if isinstance(schema_field, dict):
                alias_result = {
                    "decision": "not_needed",
                    "reason_code": "ALIAS_NOT_NEEDED",
                    "reason": "字段路径已由当前角色卡 Schema 明确定义，无需别名改写",
                }
            else:
                alias_result = {
                    "decision": "not_matched",
                    "reason_code": "ALIAS_NOT_MATCHED",
                    "reason": "未命中当前角色卡已确认或候选别名",
                }

        adjustment = _take_match(remaining_adjustments, alias_effective, nested_key="operation")
        policy_effective = copy.deepcopy(adjustment.get("applied_as")) if isinstance(adjustment, dict) else copy.deepcopy(alias_effective)
        policy_passed = _take_match(remaining_policy_operations, policy_effective) is not None
        policy_rejection = None if policy_passed or adjustment else _take_match(remaining_policy_rejections, alias_effective, nested_key="operation")
        schema_adjustments_chain, effective = _take_adjustment_chain(remaining_schema_adjustments, policy_effective)
        path = effective.get("path") if isinstance(effective, dict) else raw.get("path")
        before_exists, before = _lookup(state_before, path)
        after_exists, after = _lookup(state_after, path)

        if policy_rejection:
            reason = str(policy_rejection.get("error") or policy_rejection.get("reason") or "状态规则拒绝该操作")
            entries.append({
                "operation_id": operation_id,
                "source": source or "unknown",
                "outcome": "rejected",
                "raw_operation": copy.deepcopy(raw),
                "normalized_operation": copy.deepcopy(alias_effective),
                "field": _field_metadata(path, state_before, state_after, state_schema),
                **({"alias": alias_result} if alias_stage_enabled else {}),
                "policy": {
                    "decision": "rejected",
                    "reason_code": str(policy_rejection.get("reason_code") or _reason_code(reason, stage="policy")),
                    "reason": reason,
                },
                **({"schema": {
                    "decision": "not_attempted",
                    "reason_code": "NOT_ATTEMPTED_POLICY_REJECTED",
                    "reason": "状态规则已拒绝该操作，未进入 Formal State Schema 校验",
                }} if state_schema else {}),
                "apply": {
                    "decision": "not_attempted",
                    "reason_code": "NOT_ATTEMPTED_POLICY_REJECTED",
                    "reason": "状态规则已拒绝该操作，未进入状态引擎",
                    "before_exists": before_exists,
                    "before": before,
                    "after_exists": after_exists,
                    "after": after,
                    "changed": False,
                },
            })
            continue

        if adjustment:
            policy_reason = str(adjustment.get("reason") or "按角色卡状态规则调整操作")
            policy = {
                "decision": "adjusted",
                "reason_code": str(adjustment.get("reason_code") or _reason_code(policy_reason, stage="policy")),
                "reason": policy_reason,
                "input_operation": copy.deepcopy(alias_effective),
                "output_operation": copy.deepcopy(policy_effective),
            }
        else:
            policy = {
                "decision": "passed",
                "reason_code": "POLICY_PASSED",
                "reason": "状态规则允许该操作",
            }

        engine_rejection = _take_match(remaining_engine_rejections, policy_effective, nested_key="operation")
        if engine_rejection is None and effective != policy_effective:
            engine_rejection = _take_match(remaining_engine_rejections, effective, nested_key="operation")
        if isinstance(engine_rejection, dict) and isinstance(engine_rejection.get("normalized_operation"), dict):
            effective = copy.deepcopy(engine_rejection["normalized_operation"])
            path = effective.get("path")
            before_exists, before = _lookup(state_before, path)
            after_exists, after = _lookup(state_after, path)
        applied_operation = _take_match(remaining_applied, effective)
        schema_result: dict[str, Any] | None = None
        if state_schema:
            if schema_adjustments_chain:
                schema_codes = [
                    str(item.get("reason_code") or "SCHEMA_ADJUSTED")
                    for item in schema_adjustments_chain
                ]
                schema_reasons = [
                    str(item.get("reason") or "按 Formal State Schema 调整操作")
                    for item in schema_adjustments_chain
                ]
                schema_result = {
                    "decision": "adjusted",
                    "reason_code": schema_codes[0] if len(schema_codes) == 1 else "SCHEMA_MULTIPLE_ADJUSTMENTS",
                    "reason": "；".join(schema_reasons),
                    "input_operation": copy.deepcopy(policy_effective),
                    "output_operation": copy.deepcopy(effective),
                    "adjustments": [
                        {
                            "reason_code": code,
                            "reason": reason,
                            "input_operation": copy.deepcopy(item.get("operation")),
                            "output_operation": copy.deepcopy(item.get("applied_as")),
                        }
                        for item, code, reason in zip(schema_adjustments_chain, schema_codes, schema_reasons)
                    ],
                }
            else:
                schema_result = {
                    "decision": "passed",
                    "reason_code": "SCHEMA_PASSED",
                    "reason": "Formal State Schema 允许该操作",
                }

        if engine_rejection:
            reason = str(engine_rejection.get("error") or engine_rejection.get("reason") or "状态引擎拒绝该操作")
            rejection_code = str(engine_rejection.get("reason_code") or _reason_code(reason, stage="engine"))
            outcome = "rejected"
            if state_schema and rejection_code.startswith("SCHEMA_"):
                schema_result = {
                    "decision": "rejected",
                    "reason_code": rejection_code,
                    "reason": reason,
                }
                apply_result = {
                    "decision": "not_attempted",
                    "reason_code": "NOT_ATTEMPTED_SCHEMA_REJECTED",
                    "reason": "Formal State Schema 已拒绝该操作，未进入状态合并",
                    "before_exists": before_exists,
                    "before": before,
                    "after_exists": after_exists,
                    "after": after,
                    "changed": False,
                }
            else:
                apply_result = {
                    "decision": "rejected",
                    "reason_code": rejection_code,
                    "reason": reason,
                    "before_exists": before_exists,
                    "before": before,
                    "after_exists": after_exists,
                    "after": after,
                    "changed": False,
                }
        elif applied_operation is not None:
            changed = before_exists != after_exists or before != after
            if changed:
                outcome = "adjusted_applied" if (
                    adjustment or schema_adjustments_chain or (isinstance(alias_event, dict) and alias_effective != raw)
                ) else "applied"
                apply_result = {
                    "decision": "applied",
                    "reason_code": "APPLIED",
                    "reason": "操作通过状态引擎并已应用",
                    "before_exists": before_exists,
                    "before": before,
                    "after_exists": after_exists,
                    "after": after,
                    "changed": True,
                }
            else:
                outcome = "not_applied"
                apply_result = {
                    "decision": "not_applied",
                    "reason_code": "NO_STATE_CHANGE_AFTER_PROJECTION",
                    "reason": "操作未产生可持久化状态变化，禁止标记为已应用",
                    "before_exists": before_exists,
                    "before": before,
                    "after_exists": after_exists,
                    "after": after,
                    "changed": False,
                }
        else:
            outcome = "not_applied"
            apply_result = {
                "decision": "not_applied",
                "reason_code": "TRACE_MATCH_NOT_FOUND",
                "reason": "操作未进入最终补丁，决策链未找到对应结果",
                "before_exists": before_exists,
                "before": before,
                "after_exists": after_exists,
                "after": after,
                "changed": False,
            }

        entry = {
            "operation_id": operation_id,
            "source": source or "unknown",
            "outcome": outcome,
            "raw_operation": copy.deepcopy(raw),
            "normalized_operation": copy.deepcopy(effective),
            "field": _field_metadata(path, state_before, state_after, state_schema),
            **({"alias": alias_result} if alias_stage_enabled else {}),
            "policy": policy,
            "apply": apply_result,
        }
        if schema_result is not None:
            entry["schema"] = schema_result
        entries.append(entry)

    # Preserve unmatched diagnostics without pretending that an engine rejection
    # was a policy rejection.
    for rejection in remaining_policy_rejections:
        operation = rejection.get("operation") if isinstance(rejection, dict) else rejection
        reason = str(rejection.get("error") or rejection.get("reason") or "状态规则拒绝该操作") if isinstance(rejection, dict) else "状态规则拒绝该操作"
        path = operation.get("path") if isinstance(operation, dict) else None
        entries.append({
            "operation_id": f"op-{len(entries) + 1:03d}",
            "source": source or "unknown",
            "outcome": "rejected",
            "raw_operation": copy.deepcopy(operation),
            "normalized_operation": copy.deepcopy(operation),
            "field": _field_metadata(path, state_before, state_after, state_schema),
            "policy": {
                "decision": "rejected",
                "reason_code": _reason_code(reason, stage="policy"),
                "reason": reason,
            },
            **({"schema": {
                "decision": "not_attempted",
                "reason_code": "NOT_ATTEMPTED_POLICY_REJECTED",
                "reason": "状态规则已拒绝该操作，未进入 Formal State Schema 校验",
            }} if state_schema else {}),
            "apply": {
                "decision": "not_attempted",
                "reason_code": "NOT_ATTEMPTED_POLICY_REJECTED",
                "reason": "状态规则已拒绝该操作，未进入状态引擎",
                "changed": False,
            },
        })

    for rejection in remaining_engine_rejections:
        operation = rejection.get("operation") if isinstance(rejection, dict) else rejection
        normalized_operation = rejection.get("normalized_operation") if isinstance(rejection, dict) else None
        effective_operation = normalized_operation if isinstance(normalized_operation, dict) else operation
        reason = str(rejection.get("error") or rejection.get("reason") or "状态引擎拒绝该操作") if isinstance(rejection, dict) else "状态引擎拒绝该操作"
        path = effective_operation.get("path") if isinstance(effective_operation, dict) else None
        before_exists, before = _lookup(state_before, path)
        after_exists, after = _lookup(state_after, path)
        rejection_code = _reason_code(reason, stage="engine")
        schema_rejected = bool(state_schema) and rejection_code.startswith("SCHEMA_")
        entry = {
            "operation_id": f"op-{len(entries) + 1:03d}",
            "source": source or "unknown",
            "outcome": "rejected",
            "raw_operation": copy.deepcopy(operation),
            "normalized_operation": copy.deepcopy(effective_operation),
            "field": _field_metadata(path, state_before, state_after, state_schema),
            "policy": {
                "decision": "passed",
                "reason_code": "POLICY_PASSED",
                "reason": "状态规则允许该操作",
            },
            "apply": {
                "decision": "not_attempted" if schema_rejected else "rejected",
                "reason_code": "NOT_ATTEMPTED_SCHEMA_REJECTED" if schema_rejected else rejection_code,
                "reason": "Formal State Schema 已拒绝该操作，未进入状态合并" if schema_rejected else reason,
                "before_exists": before_exists,
                "before": before,
                "after_exists": after_exists,
                "after": after,
                "changed": False,
            },
        }
        if state_schema:
            entry["schema"] = {
                "decision": "rejected" if schema_rejected else "passed",
                "reason_code": rejection_code if schema_rejected else "SCHEMA_PASSED",
                "reason": reason if schema_rejected else "Formal State Schema 允许该操作",
            }
        entries.append(entry)

    return entries
