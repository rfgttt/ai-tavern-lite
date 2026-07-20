from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

from ..tavern_compat.initial_state import extract_card_variables, merge_card_variables, project_card_variables
from .state_policy import apply_stage_projection
from .state_aliases import resolve_alias_operation
from .state_schema import (
    canonicalize_patch_operation,
    clamp_schema_number,
    validate_patch_operation,
    validate_state_against_schema,
)


MAX_PATCH_OPERATIONS = 64
MAX_PATH_DEPTH = 16
MAX_STATE_BYTES = 512 * 1024
_FORBIDDEN_KEYS = {"__proto__", "prototype", "constructor"}


def serialize_state_document(state: dict, schema: dict | None = None) -> str:
    """Validate and serialize a complete runtime state document."""
    if not isinstance(state, dict):
        raise ValueError("状态根节点必须是对象")

    stack: list[Any] = [state]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for raw_key, value in current.items():
                key = str(raw_key)
                if key in _FORBIDDEN_KEYS:
                    raise ValueError(f"状态包含禁止字段: {key}")
                if len(key) > 160:
                    raise ValueError("状态字段名称过长")
                stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)

    try:
        serialized = json.dumps(state, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"状态不是有效 JSON: {error}") from error
    if len(serialized.encode("utf-8")) > MAX_STATE_BYTES:
        raise ValueError("状态大小超过限制")
    if schema:
        validation = validate_state_against_schema(state, schema)
        if validation["errors"]:
            first = validation["errors"][0]
            raise ValueError(f"状态 Schema 校验失败 {first.get('path', '')}: {first.get('message', '未知错误')}")
    return serialized


@dataclass
class PatchResult:
    state: dict
    applied: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    adjusted: list[dict] = field(default_factory=list)
    alias_events: list[dict] = field(default_factory=list)


def _default_dnd_character(name: str = "初始模板") -> dict:
    return {
        "姓名": name,
        "玩家名": "",
        "职业": "",
        "种族": "人类",
        "阵营": "绝对中立",
        "等级": 1,
        "熟练加值": 2,
        "护甲等级": {"总值": 10, "描述": ""},
        "生命值": {"当前": 10, "最大": 10, "临时": 0},
        "状态": {},
        "资源": {},
        "钱币": {"白金": 0, "金币": 0, "银币": 0, "铜币": 0},
        "物品": {"武器": {}, "护甲": {}, "奇物": {}, "杂物": {}},
        "施法": {"关键属性": "智力", "法术位": {}, "法术书": {}},
        "笔记": {},
    }


def build_initial_state(profile: dict, normalized: dict, username: str = "用户") -> dict:
    """Build a minimal state shell; card data and real story changes activate panels."""
    profile = profile if isinstance(profile, dict) else {}
    normalized = normalized if isinstance(normalized, dict) else {}
    mode = profile.get("mode", "general")
    scenario = str(normalized.get("scenario", "")).strip()
    name = str(normalized.get("name", "角色")).strip() or "角色"

    state = {
        "runtime_version": 2,
        "mode": mode,
        "scene": {"location": scenario} if scenario else {},
        "character": {"name": name},
        "relationship": {
            "affection": 0,
            "trust": 0,
            "tension": 0,
            "stage": "初识",
        },
        "player": {"name": username or "用户"},
        "party": [],
        "quests": [],
        "inventory": [],
        "combat": {},
        "custom": {},
    }

    if mode == "adventure":
        state["custom"] = {
            "当前角色ID": "初始模板",
            "角色列表": {"初始模板": _default_dnd_character()},
        }

    initial_variables = extract_card_variables(normalized)
    state = merge_card_variables(state, initial_variables.variables)
    return apply_stage_projection(state, profile.get("state_policy"))


def _decode_pointer(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("path 必须是以 / 开头的 JSON Pointer")
    if path == "/":
        return [""]
    parts = [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]
    if len(parts) > MAX_PATH_DEPTH:
        raise ValueError("path 层级过深")
    for part in parts:
        if part in _FORBIDDEN_KEYS or part.startswith("_"):
            raise ValueError("path 包含禁止字段")
        if len(part) > 160:
            raise ValueError("path 字段过长")
    return parts


def _list_index(part: str, length: int, allow_append: bool = False) -> int:
    if part == "-" and allow_append:
        return length
    try:
        index = int(part)
    except (TypeError, ValueError) as exc:
        raise ValueError("数组索引无效") from exc
    if index < 0 or index > length or (not allow_append and index >= length):
        raise ValueError("数组索引越界")
    return index


def _resolve_parent(root: Any, parts: list[str], create: bool = False) -> tuple[Any, str]:
    if not parts:
        raise ValueError("不允许替换整个状态根节点")
    current = root
    for part in parts[:-1]:
        if isinstance(current, dict):
            if part not in current:
                if not create:
                    raise ValueError("路径不存在")
                current[part] = {}
            current = current[part]
        elif isinstance(current, list):
            current = current[_list_index(part, len(current))]
        else:
            raise ValueError("路径穿过了非容器值")
    return current, parts[-1]


def _get_value(root: Any, parts: list[str]) -> Any:
    current = root
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                raise ValueError("路径不存在")
            current = current[part]
        elif isinstance(current, list):
            current = current[_list_index(part, len(current))]
        else:
            raise ValueError("路径穿过了非容器值")
    return current


def _clamp_number(path: str, value: float, state: dict, schema: dict | None = None) -> float | int:
    lower_path = path.lower()
    path_parts = [part.replace("~1", "/").replace("~0", "~") for part in path.split("/") if part]
    semantic_key = ""
    for part in reversed(path_parts):
        if not str(part).isdigit() and part != "-":
            semantic_key = str(part).lower()
            break
    if any(lower_path.endswith(suffix) for suffix in (
        "/relationship/affection",
        "/relationship/trust",
        "/relationship/tension",
        "/character/energy",
    )) or semantic_key in {
        "好感度", "好感", "affection", "favorability", "affinity",
        "害怕值", "恐惧值", "畏惧", "fear",
        "依赖值", "依赖度", "dependence", "dependency",
        "信任度", "信任", "trust", "亲密度", "亲密", "intimacy",
    }:
        value = max(0, min(100, value))
    elif lower_path.endswith("/player/level") or path.endswith("/等级"):
        value = max(1, min(20, value))
    elif lower_path.endswith("/player/hp"):
        max_hp = state.get("player", {}).get("max_hp", value)
        if isinstance(max_hp, (int, float)):
            value = max(0, min(max_hp, value))
    elif lower_path.endswith("/player/max_hp"):
        value = max(1, min(1_000_000, value))
    elif lower_path.endswith("/player/ac") or path.endswith("/护甲等级/总值"):
        value = max(0, min(99, value))
    elif path.endswith("/生命值/当前"):
        max_path = path.rsplit("/", 1)[0] + "/最大"
        try:
            maximum = _get_value(state, _decode_pointer(max_path))
        except ValueError:
            maximum = value
        if isinstance(maximum, (int, float)):
            value = max(0, min(maximum, value))
    elif path.endswith("/生命值/最大"):
        value = max(1, min(1_000_000, value))

    value = clamp_schema_number(path, value, schema)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _set_value(root: dict, parts: list[str], value: Any, *, create: bool, append: bool = False) -> None:
    parent, key = _resolve_parent(root, parts, create=create)
    if isinstance(parent, dict):
        if not create and key not in parent:
            raise ValueError("路径不存在")
        parent[key] = value
    elif isinstance(parent, list):
        index = _list_index(key, len(parent), allow_append=append)
        if index == len(parent):
            parent.append(value)
        else:
            parent[index] = value
    else:
        raise ValueError("父路径不是容器")


def _remove_value(root: dict, parts: list[str]) -> None:
    parent, key = _resolve_parent(root, parts, create=False)
    if isinstance(parent, dict):
        if key not in parent:
            raise ValueError("路径不存在")
        del parent[key]
    elif isinstance(parent, list):
        del parent[_list_index(key, len(parent))]
    else:
        raise ValueError("父路径不是容器")


def apply_patch(
    state: dict,
    operations: list[dict],
    schema: dict | None = None,
    aliases: dict | None = None,
) -> PatchResult:
    """Apply a constrained JSON-patch-like operation list to a deep copy of state."""
    original = copy.deepcopy(state if isinstance(state, dict) else {})
    working = copy.deepcopy(original)
    applied: list[dict] = []
    rejected: list[dict] = []
    adjusted: list[dict] = []
    alias_events: list[dict] = []

    if not isinstance(operations, list):
        return PatchResult(original, [], [{"operation": operations, "error": "patch 必须是数组"}])

    for operation in operations[:MAX_PATCH_OPERATIONS]:
        if not isinstance(operation, dict):
            rejected.append({"operation": operation, "error": "操作必须是对象"})
            continue
        normalized_operation = copy.deepcopy(operation)
        try:
            projected_before = project_card_variables(working)
            normalized_operation, alias_event = resolve_alias_operation(operation, schema, aliases)
            if alias_event:
                alias_events.append(copy.deepcopy(alias_event))
                if alias_event.get("decision") == "invalid":
                    raise ValueError(str(alias_event.get("reason") or "已确认别名目标无效"))
            normalized_operation, path_adjustment = canonicalize_patch_operation(normalized_operation, schema)
            op = str(normalized_operation.get("op", "")).lower()
            path = str(normalized_operation.get("path", ""))
            parts = _decode_pointer(path)
            value = copy.deepcopy(normalized_operation.get("value"))
            accepted_operation = copy.deepcopy(normalized_operation)
            schema_adjustments: list[dict[str, Any]] = []
            if path_adjustment:
                schema_adjustments.append(path_adjustment)
            validate_patch_operation(working, normalized_operation, schema)

            if op in {"increment", "delta"}:
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise ValueError("增量值必须是数字")
                create_missing = False
                try:
                    current = _get_value(working, parts)
                except ValueError:
                    parent, key = _resolve_parent(working, parts, create=False)
                    if not isinstance(parent, dict) or key in parent:
                        raise
                    current = 0
                    create_missing = True
                if not isinstance(current, (int, float)) or isinstance(current, bool):
                    raise ValueError("增量操作目标必须是数字")
                next_value = _clamp_number(path, current + value, working, schema)
                actual_delta = next_value - current
                if schema and actual_delta == 0 and value != 0:
                    raise ValueError("状态 Schema 数值已达到边界，操作未生效")
                if actual_delta != value:
                    accepted_operation["value"] = actual_delta
                    schema_adjustments.append({
                        "operation": copy.deepcopy(normalized_operation),
                        "applied_as": copy.deepcopy(accepted_operation),
                        "reason_code": "SCHEMA_RANGE_CLAMPED",
                        "reason": "按 Formal State Schema 数值范围调整操作",
                    })
                _set_value(working, parts, next_value, create=create_missing)
            elif op == "replace":
                original_value = copy.deepcopy(value)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    value = _clamp_number(path, value, working, schema)
                if value != original_value:
                    accepted_operation["value"] = copy.deepcopy(value)
                    schema_adjustments.append({
                        "operation": copy.deepcopy(normalized_operation),
                        "applied_as": copy.deepcopy(accepted_operation),
                        "reason_code": "SCHEMA_RANGE_CLAMPED",
                        "reason": "按 Formal State Schema 数值范围调整操作",
                    })
                _set_value(working, parts, value, create=False)
            elif op in {"add", "insert"}:
                original_value = copy.deepcopy(value)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    value = _clamp_number(path, value, working, schema)
                if value != original_value:
                    accepted_operation["value"] = copy.deepcopy(value)
                    schema_adjustments.append({
                        "operation": copy.deepcopy(normalized_operation),
                        "applied_as": copy.deepcopy(accepted_operation),
                        "reason_code": "SCHEMA_RANGE_CLAMPED",
                        "reason": "按 Formal State Schema 数值范围调整操作",
                    })
                _set_value(working, parts, value, create=True, append=True)
            elif op == "append":
                target = _get_value(working, parts)
                if not isinstance(target, list):
                    raise ValueError("append 目标必须是数组")
                target.append(value)
            elif op == "insert_at":
                target = _get_value(working, parts)
                if not isinstance(target, list):
                    raise ValueError("insert_at 目标必须是数组")
                index = operation.get("index")
                if not isinstance(index, int) or isinstance(index, bool):
                    raise ValueError("insert_at 索引必须是整数")
                if index < 0 or index > len(target):
                    raise ValueError("insert_at 索引越界")
                target.insert(index, value)
            elif op == "remove_at":
                target = _get_value(working, parts)
                if not isinstance(target, list):
                    raise ValueError("remove_at 目标必须是数组")
                index = operation.get("index")
                if not isinstance(index, int) or isinstance(index, bool):
                    raise ValueError("remove_at 索引必须是整数")
                if index < 0 or index >= len(target):
                    raise ValueError("remove_at 索引越界")
                del target[index]
            elif op == "remove_value":
                target = _get_value(working, parts)
                if isinstance(target, list):
                    try:
                        target.remove(value)
                    except ValueError as error:
                        raise ValueError("数组中不存在待移除值") from error
                elif isinstance(target, dict):
                    key = str(value)
                    if key not in target:
                        raise ValueError("对象中不存在待移除键")
                    del target[key]
                else:
                    raise ValueError("remove_value 目标必须是数组或对象")
            elif op == "remove":
                _remove_value(working, parts)
            else:
                raise ValueError(f"不支持的操作: {op or '空'}")

            projected_after = project_card_variables(working)
            if projected_after == projected_before:
                raise ValueError("替换值与当前状态相同，已忽略无效操作")
            working = projected_after
            if len(json.dumps(working, ensure_ascii=False).encode("utf-8")) > MAX_STATE_BYTES:
                raise ValueError("状态大小超过限制")
            applied.append(copy.deepcopy(accepted_operation))
            adjusted.extend(copy.deepcopy(schema_adjustments))
        except (ValueError, TypeError) as error:
            # An individual rejected operation must not partially mutate state.
            working = copy.deepcopy(original)
            for accepted in applied:
                replay = apply_patch(working, [accepted], schema=schema, aliases=aliases)
                if replay.applied:
                    working = replay.state
            rejection = {"operation": copy.deepcopy(operation), "error": str(error)}
            if normalized_operation != operation:
                rejection["normalized_operation"] = copy.deepcopy(normalized_operation)
            rejected.append(rejection)

    if len(operations) > MAX_PATCH_OPERATIONS:
        rejected.append({"operation": "overflow", "error": f"每轮最多 {MAX_PATCH_OPERATIONS} 个操作"})
    return PatchResult(project_card_variables(working), applied, rejected, adjusted, alias_events)
