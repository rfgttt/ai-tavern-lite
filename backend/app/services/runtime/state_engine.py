from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

from ..tavern_compat.initial_state import extract_card_variables, merge_card_variables, project_card_variables


MAX_PATCH_OPERATIONS = 64
MAX_PATH_DEPTH = 16
MAX_STATE_BYTES = 512 * 1024
_FORBIDDEN_KEYS = {"__proto__", "prototype", "constructor"}


@dataclass
class PatchResult:
    state: dict
    applied: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)


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
    return state


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


def _clamp_number(path: str, value: float, state: dict) -> float | int:
    lower_path = path.lower()
    if any(lower_path.endswith(suffix) for suffix in (
        "/relationship/affection",
        "/relationship/trust",
        "/relationship/tension",
        "/character/energy",
    )):
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


def apply_patch(state: dict, operations: list[dict]) -> PatchResult:
    """Apply a constrained JSON-patch-like operation list to a deep copy of state."""
    original = copy.deepcopy(state if isinstance(state, dict) else {})
    working = copy.deepcopy(original)
    applied: list[dict] = []
    rejected: list[dict] = []

    if not isinstance(operations, list):
        return PatchResult(original, [], [{"operation": operations, "error": "patch 必须是数组"}])

    for operation in operations[:MAX_PATCH_OPERATIONS]:
        if not isinstance(operation, dict):
            rejected.append({"operation": operation, "error": "操作必须是对象"})
            continue
        try:
            op = str(operation.get("op", "")).lower()
            path = str(operation.get("path", ""))
            parts = _decode_pointer(path)
            value = copy.deepcopy(operation.get("value"))

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
                next_value = _clamp_number(path, current + value, working)
                _set_value(working, parts, next_value, create=create_missing)
            elif op == "replace":
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    value = _clamp_number(path, value, working)
                _set_value(working, parts, value, create=False)
            elif op in {"add", "insert"}:
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    value = _clamp_number(path, value, working)
                _set_value(working, parts, value, create=True, append=True)
            elif op == "remove":
                _remove_value(working, parts)
            else:
                raise ValueError(f"不支持的操作: {op or '空'}")

            if len(json.dumps(working, ensure_ascii=False).encode("utf-8")) > MAX_STATE_BYTES:
                raise ValueError("状态大小超过限制")
            applied.append(copy.deepcopy(operation))
        except (ValueError, TypeError) as error:
            # An individual rejected operation must not partially mutate state.
            working = copy.deepcopy(original)
            for accepted in applied:
                replay = apply_patch(working, [accepted])
                if replay.applied:
                    working = replay.state
            rejected.append({"operation": copy.deepcopy(operation), "error": str(error)})

    if len(operations) > MAX_PATCH_OPERATIONS:
        rejected.append({"operation": "overflow", "error": f"每轮最多 {MAX_PATCH_OPERATIONS} 个操作"})
    return PatchResult(project_card_variables(working), applied, rejected)
