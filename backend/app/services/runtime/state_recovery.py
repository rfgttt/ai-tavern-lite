from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


MAX_RECOVERY_OPERATIONS = 16
MAX_RECOVERY_RULE_CHARS = 4_000
MAX_RECOVERY_NARRATIVE_CHARS = 4_000
MAX_RECOVERY_USER_CHARS = 1_500
MAX_RECOVERY_STATE_CHARS = 16_000
MAX_RECOVERY_OUTPUT_TOKENS = 1_024
MAX_RECOVERY_VALUE_CHARS = 1_000

_RELATIONSHIP_KEYS = {
    "好感度", "好感", "affection", "favorability", "affinity",
    "害怕值", "恐惧值", "畏惧", "fear",
    "依赖值", "依赖度", "dependence", "dependency",
    "信任度", "信任", "trust", "亲密度", "亲密", "intimacy",
}


@dataclass
class RecoveryOutcome:
    attempted: bool = False
    reason: str = ""
    operations: list[dict[str, Any]] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    response_characters: int = 0
    http_completed: bool = False
    finish_reason: str = ""
    response_type: str = ""
    error_type: str = ""
    reasoning_characters: int = 0
    reasoning_tokens: int = 0
    completion_tokens: int = 0
    requested_max_tokens: int = 0
    request_profile: str = ""


@dataclass(frozen=True)
class AllowedTarget:
    path: str
    kind: str
    value: Any


def declared_state_protocol(profile: dict[str, Any] | None) -> bool:
    profile = profile if isinstance(profile, dict) else {}
    capabilities = profile.get("capabilities")
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    return bool(
        capabilities.get("mvu_command_protocol")
        or capabilities.get("mvu_json_patch_protocol")
    )


def should_attempt_recovery(
    *,
    profile: dict[str, Any] | None,
    enabled: bool,
    final_status: str,
    primary_operations: list[dict[str, Any]],
    provider_cancelled: bool,
) -> tuple[bool, str]:
    if not enabled:
        return False, "disabled"
    if final_status != "complete":
        return False, f"primary_{final_status or 'incomplete'}"
    if provider_cancelled:
        return False, "provider_cancelled"
    if not declared_state_protocol(profile):
        return False, "card_has_no_declared_state_protocol"
    if primary_operations:
        return False, "primary_response_has_state_update"
    return True, "primary_response_missing_state_update"


def _pointer_part(value: Any) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _is_descriptor_tuple(value: list[Any]) -> bool:
    return (
        len(value) == 2
        and isinstance(value[1], str)
        and isinstance(value[0], (dict, list, str, int, float, bool, type(None)))
    )


def _clean_preview(value: Any) -> Any:
    if isinstance(value, list):
        return [
            _clean_preview(item)
            for item in value
            if item != "$__META_EXTENSIBLE__$"
        ][:12]
    if isinstance(value, dict):
        return {
            str(key): _clean_preview(item)
            for key, item in list(value.items())[:20]
            if not str(key).startswith(("$", "_"))
        }
    if isinstance(value, str):
        return value[:500]
    return value


def _walk_targets(value: Any, path: str, output: list[AllowedTarget]) -> None:
    if len(output) >= 96:
        return
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key)
            if key.startswith(("$", "_")) or key in {"runtime_version", "mode"}:
                continue
            _walk_targets(item, f"{path}/{_pointer_part(key)}", output)
        return
    if isinstance(value, list):
        if _is_descriptor_tuple(value):
            _walk_targets(value[0], f"{path}/0", output)
            return
        output.append(AllowedTarget(path=path, kind="array", value=_clean_preview(value)))
        return
    if isinstance(value, bool):
        kind = "boolean"
    elif isinstance(value, (int, float)):
        kind = "number"
    elif value is None:
        kind = "null"
    else:
        kind = "string"
    output.append(AllowedTarget(path=path, kind=kind, value=_clean_preview(value)))


def allowed_state_targets(state: dict[str, Any] | None) -> dict[str, AllowedTarget]:
    state = state if isinstance(state, dict) else {}
    targets: list[AllowedTarget] = []
    custom = state.get("custom")
    if isinstance(custom, dict) and any(not str(key).startswith(("$", "_")) for key in custom):
        _walk_targets(custom, "/custom", targets)
    else:
        for root in ("scene", "relationship", "character", "quests", "inventory", "combat"):
            if root in state:
                _walk_targets(state[root], f"/{root}", targets)
    return {target.path: target for target in targets if target.path and target.path != "/custom"}


def _semantic_key(path: str) -> str:
    for part in reversed(path.split("/")):
        decoded = part.replace("~1", "/").replace("~0", "~")
        if decoded and not decoded.isdigit() and decoded != "-":
            return decoded.lower()
    return ""


def _bounded_value(value: Any) -> Any:
    serialized = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(serialized) > MAX_RECOVERY_VALUE_CHARS:
        raise ValueError("操作值过长")
    return value


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def validate_recovery_operations(
    payload: Any,
    targets: dict[str, AllowedTarget],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    if not isinstance(payload, dict):
        return [], [], ["状态提取结果必须是 JSON 对象"]
    raw_operations = payload.get("operations")
    if not isinstance(raw_operations, list):
        return [], [], ["状态提取结果缺少 operations 数组"]

    accepted: list[dict[str, Any]] = []
    events: list[str] = []
    errors: list[str] = []
    for raw in raw_operations[:MAX_RECOVERY_OPERATIONS]:
        if not isinstance(raw, dict):
            errors.append("状态提取操作必须是对象")
            continue
        try:
            op = str(raw.get("op", "")).strip().lower()
            path = str(raw.get("path", "")).strip()
            target = targets.get(path)
            if target is None:
                raise ValueError("操作路径不在角色卡声明状态中")
            value = _bounded_value(raw.get("value"))

            if op in {"add", "delta"}:
                op = "increment" if target.kind == "number" else "append"
            if op == "increment":
                if target.kind != "number" or isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("increment 只能用于数字字段")
                if _semantic_key(path) in _RELATIONSHIP_KEYS:
                    value = max(-2, min(2, value))
                operation = {"op": "increment", "path": path, "value": value}
            elif op == "replace":
                if target.kind == "array":
                    raise ValueError("数组字段不能整体 replace")
                if target.kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
                    raise ValueError("数字字段的新值必须是数字")
                if target.kind == "boolean" and not isinstance(value, bool):
                    raise ValueError("布尔字段的新值必须是布尔值")
                if target.kind == "string" and not isinstance(value, str):
                    raise ValueError("文本字段的新值必须是字符串")
                operation = {"op": "replace", "path": path, "value": value}
            elif op == "append":
                if target.kind != "array":
                    raise ValueError("append 只能用于数组字段")
                operation = {"op": "append", "path": path, "value": value}
            elif op == "remove_value":
                if target.kind != "array":
                    raise ValueError("remove_value 只能用于数组字段")
                operation = {"op": "remove_value", "path": path, "value": value}
            else:
                raise ValueError("仅允许 increment、replace、append、remove_value")

            if operation not in accepted:
                accepted.append(operation)
            reason = str(raw.get("reason", "")).strip()
            if reason and reason not in events:
                events.append(reason[:300])
        except (TypeError, ValueError) as error:
            errors.append(str(error))

    if len(raw_operations) > MAX_RECOVERY_OPERATIONS:
        errors.append(f"状态提取每轮最多 {MAX_RECOVERY_OPERATIONS} 个操作")
    return accepted, events[:12], errors[:20]


def _extract_json_object(text: str) -> Any:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(cleaned):
            if char != "{":
                continue
            try:
                value, _ = decoder.raw_decode(cleaned[index:])
                return value
            except json.JSONDecodeError:
                continue
        raise ValueError("状态提取模型没有返回有效 JSON")


def build_recovery_messages(
    *,
    state_before: dict[str, Any],
    user_message: str,
    assistant_narrative: str,
    card_rules: str,
    targets: dict[str, AllowedTarget],
) -> list[dict[str, str]]:
    target_rows = [
        {"path": item.path, "kind": item.kind, "current": item.value}
        for item in targets.values()
    ]
    state_text = json.dumps(target_rows, ensure_ascii=False, separators=(",", ":"))
    if len(state_text) > MAX_RECOVERY_STATE_CHARS:
        state_text = state_text[:MAX_RECOVERY_STATE_CHARS]
    rules = str(card_rules or "")[:MAX_RECOVERY_RULE_CHARS]
    user_text = str(user_message or "")[-MAX_RECOVERY_USER_CHARS:]
    narrative = str(assistant_narrative or "")[-MAX_RECOVERY_NARRATIVE_CHARS:]

    system = """你是本地角色状态差异提取器。你的唯一任务是根据本轮用户行动和已经生成的角色回复，提取确实发生的状态变化。
只输出一个严格 json 对象，不要 Markdown，不要解释，不要代码，不要复述剧情。
JSON 结构必须是：{"operations":[{"op":"increment|replace|append|remove_value","path":"允许路径","value":值,"reason":"简短原因"}]}。
只能使用给出的允许路径。数字增减使用 increment；数组新增使用 append；数组删除使用 remove_value；文本、日期、时间和地点使用 replace。
不得创造字段，不得修改技术元数据，不得猜测没有在剧情中明确发生的变化。没有可靠变化时输出 {"operations":[]}。
关系数值每轮变化必须保守；角色卡规则更严格时服从角色卡规则。

空操作示例：{"operations":[]}
更新示例：{"operations":[{"op":"increment","path":"/custom/角色/好感度/0","value":1,"reason":"用户进行了明确且持续的照顾"}]}"""
    user = f"""【允许更新的字段与当前值】
{state_text}

【角色卡变量规则】
{rules or '未提供额外规则；仅记录明确发生的事实。'}

【本轮用户消息】
{user_text}

【本轮角色可见回复】
{narrative}

现在仅输出严格 JSON。"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def recover_missing_state_update(
    *,
    provider: Any,
    state_before: dict[str, Any],
    user_message: str,
    assistant_narrative: str,
    card_rules: str,
    custom_headers: dict[str, str] | None,
) -> RecoveryOutcome:
    outcome = RecoveryOutcome(attempted=True, reason="primary_response_missing_state_update")
    targets = allowed_state_targets(state_before)
    if not targets:
        outcome.reason = "fallback_no_targets"
        outcome.errors.append("角色卡没有可安全更新的已声明状态字段")
        return outcome

    messages = build_recovery_messages(
        state_before=state_before,
        user_message=user_message,
        assistant_narrative=assistant_narrative,
        card_rules=card_rules,
        targets=targets,
    )
    try:
        result = await provider.complete_once(
            messages=messages,
            temperature=0.0,
            top_p=None,
            max_tokens=MAX_RECOVERY_OUTPUT_TOKENS,
            custom_headers=custom_headers,
        )
        outcome.http_completed = True
        if bool(getattr(provider, "cancelled", False)):
            outcome.reason = "fallback_cancelled"
            outcome.errors.append("状态提取已取消")
            return outcome
        outcome.finish_reason = str(getattr(result, "finish_reason", "") or "")[:80]
        outcome.response_type = str(getattr(result, "response_type", type(result).__name__) or "")[:120]
        outcome.reasoning_characters = _nonnegative_int(getattr(result, "reasoning_characters", 0))
        outcome.reasoning_tokens = _nonnegative_int(getattr(result, "reasoning_tokens", 0))
        outcome.completion_tokens = _nonnegative_int(getattr(result, "completion_tokens", 0))
        outcome.requested_max_tokens = _nonnegative_int(getattr(result, "requested_max_tokens", 0))
        outcome.request_profile = str(getattr(result, "request_profile", "") or "")[:80]
        raw = str(getattr(result, "content", "") or "")
        outcome.response_characters = len(raw)

        if outcome.finish_reason == "length":
            if not raw.strip() and (outcome.reasoning_characters > 0 or outcome.reasoning_tokens > 0):
                outcome.reason = "fallback_reasoning_budget_exhausted"
                outcome.errors.append("状态提取推理占满输出预算，未生成最终 JSON")
            else:
                outcome.reason = "fallback_output_truncated"
                outcome.errors.append("状态提取输出达到长度上限，结果未应用")
            return outcome
        if outcome.finish_reason == "content_filter":
            outcome.reason = "fallback_content_filtered"
            outcome.errors.append("状态提取结果被上游内容策略拦截")
            return outcome
        if outcome.finish_reason == "insufficient_system_resource":
            outcome.reason = "fallback_upstream_resource_interrupted"
            outcome.errors.append("状态提取被上游资源限制中断")
            return outcome
        if not raw.strip():
            outcome.reason = "fallback_empty_response"
            outcome.errors.append("状态提取模型返回空内容")
            return outcome
        if len(raw) > 8_000:
            outcome.reason = "fallback_response_too_long"
            outcome.errors.append("状态提取输出超过长度限制")
            return outcome
        try:
            payload = _extract_json_object(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            outcome.reason = "fallback_invalid_json"
            outcome.error_type = error.__class__.__name__
            outcome.errors.append("状态提取模型没有返回有效 JSON")
            return outcome
        operations, events, errors = validate_recovery_operations(payload, targets)
        outcome.operations = operations
        outcome.events = events
        outcome.errors.extend(errors)
        if operations:
            outcome.reason = "fallback_applied"
        elif errors:
            outcome.reason = "fallback_no_valid_operations"
        else:
            outcome.reason = "fallback_no_operations"
        return outcome
    except Exception as error:  # The main narrative must survive a fallback failure.
        outcome.reason = "fallback_provider_error"
        outcome.error_type = error.__class__.__name__
        outcome.errors.append(f"状态提取提供商请求失败: {error.__class__.__name__}")
        return outcome
