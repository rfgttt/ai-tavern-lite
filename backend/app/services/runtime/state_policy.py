from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..tavern_compat.initial_state import extract_card_variables, project_card_variables


_RELATION_ALIASES: dict[str, tuple[str, ...]] = {
    "affection": ("好感度", "好感", "affection", "favorability", "affinity"),
    "fear": ("害怕值", "恐惧值", "畏惧", "fear"),
    "dependence": ("依赖值", "依赖度", "dependence", "dependency"),
    "trust": ("信任度", "信任", "trust"),
    "intimacy": ("亲密度", "亲密", "intimacy"),
}


@dataclass
class StatePolicyResult:
    operations: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    adjusted: list[dict[str, Any]] = field(default_factory=list)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _pointer_escape(value: str) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _all_lore_entries(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    book = _dict(normalized.get("character_book"))
    return [item for item in _list(book.get("entries")) if isinstance(item, dict)]


def _relationship_paths(normalized: dict[str, Any]) -> dict[str, list[str]]:
    variables = extract_card_variables(normalized).variables
    if not variables:
        return {}

    character_name = str(normalized.get("name", "")).strip()
    candidates: list[tuple[str, dict[str, Any]]] = []
    if character_name and isinstance(variables.get(character_name), dict):
        candidates.append((character_name, variables[character_name]))
    for root, value in variables.items():
        if not isinstance(value, dict) or any(root == item[0] for item in candidates):
            continue
        lowered = {str(key).lower() for key in value}
        if any(alias.lower() in lowered for aliases in _RELATION_ALIASES.values() for alias in aliases):
            candidates.append((str(root), value))

    paths: dict[str, list[str]] = {}
    for root, data in candidates:
        for semantic, aliases in _RELATION_ALIASES.items():
            for key in data:
                if str(key).lower() not in {alias.lower() for alias in aliases}:
                    continue
                value = data[key]
                suffix = "/0" if isinstance(value, list) and len(value) == 2 and isinstance(value[1], str) else ""
                paths.setdefault(semantic, []).append(
                    f"/custom/{_pointer_escape(root)}/{_pointer_escape(str(key))}{suffix}"
                )
                break

    for semantic in _RELATION_ALIASES:
        paths.setdefault(semantic, []).append(f"/relationship/{semantic}")
    return paths


def _stage_policy(text: str) -> dict[str, Any]:
    if "getwi(" not in text.lower() or not re.search(r"affection\s*>=\s*81|好感度.*81", text, re.IGNORECASE):
        return {}
    return {
        "enabled": True,
        "terminal": {"affection": 100, "fear": 0, "dependence": 100, "label": "阶段06 · 圆满"},
        "thresholds": [
            {"minimum": 81, "label": "阶段05 · 深度依恋"},
            {"minimum": 61, "label": "阶段04 · 信任重建"},
            {"minimum": 41, "label": "阶段03 · 逐渐亲近"},
            {"minimum": 21, "label": "阶段02 · 试探信任"},
            {"minimum": 0, "label": "基础阶段 · 极度恐惧"},
        ],
    }


def extract_state_policy(normalized: dict[str, Any]) -> dict[str, Any]:
    """Extract declarative limits from card text without executing card code."""

    normalized = normalized if isinstance(normalized, dict) else {}
    entries = _all_lore_entries(normalized)
    rule_text = "\n".join(
        str(entry.get("content", ""))
        for entry in entries
        if any(token in str(entry.get("comment", "")).lower() for token in ("变量", "mvu", "控制器"))
        or any(token in str(entry.get("content", "")).lower() for token in ("updatevariable", "_.add", "getwi("))
    )
    if not rule_text:
        return {}

    per_turn_match = re.search(r"每轮最多变化\s*(\d+)\s*点", rule_text)
    per_day_match = re.search(r"(?:一天|每日)最多(?:累计)?变化\s*(\d+)\s*点", rule_text)
    terminal_lock = bool(
        re.search(r"(?:最终阶段锁定|数值锁定不再变化|三个数值完全锁定)", rule_text)
        and "100" in rule_text
        and "害怕值" in rule_text
    )
    paths = _relationship_paths(normalized)
    stage = _stage_policy(rule_text)

    referenced_names = set(re.findall(r"getwi\(\s*(?:null|[^,]+)\s*,\s*['\"]([^'\"]+)['\"]", rule_text, re.IGNORECASE))
    referenced_chars = sum(
        len(str(entry.get("content", "")))
        for entry in entries
        if str(entry.get("comment", "")).strip() in referenced_names
    )
    recommended_context = 16_384 if referenced_chars >= 10_000 else 12_288 if referenced_chars >= 5_000 else 8_192

    enabled = bool(paths and (per_turn_match or per_day_match or terminal_lock or stage))
    if not enabled:
        return {}
    return {
        "version": 1,
        "enabled": True,
        "relationship_paths": paths,
        "per_turn_absolute_limit": int(per_turn_match.group(1)) if per_turn_match else None,
        "per_day_absolute_limit": int(per_day_match.group(1)) if per_day_match else None,
        "terminal_lock": {
            "enabled": terminal_lock,
            "affection": 100,
            "fear": 0,
            "dependence": 100,
        },
        "stage_projection": stage,
        "recommended_context_window": recommended_context,
        "source": "card_declared_rules",
    }


def apply_stage_projection(state: dict[str, Any], policy: dict[str, Any] | None) -> dict[str, Any]:
    result = project_card_variables(state)
    stage_policy = _dict(_dict(policy).get("stage_projection"))
    if not stage_policy.get("enabled"):
        return result
    relationship = _dict(result.get("relationship"))
    affection = relationship.get("affection")
    fear = relationship.get("fear")
    dependence = relationship.get("dependence")
    if not isinstance(affection, (int, float)):
        return result

    terminal = _dict(stage_policy.get("terminal"))
    if (
        affection == terminal.get("affection")
        and fear == terminal.get("fear")
        and dependence == terminal.get("dependence")
    ):
        label = str(terminal.get("label", "阶段06"))
    else:
        label = ""
        for item in _list(stage_policy.get("thresholds")):
            if isinstance(item, dict) and affection >= float(item.get("minimum", 0)):
                label = str(item.get("label", ""))
                break
    if label:
        relationship["stage"] = label
        result["relationship"] = relationship
    return result


def _decode_pointer(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/"):
        return []
    return [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]


def _lookup(root: Any, path: str) -> Any:
    current = root
    for part in _decode_pointer(path):
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(path)
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


def _semantic_for_path(path: str, policy: dict[str, Any]) -> str | None:
    paths = _dict(policy.get("relationship_paths"))
    for semantic, values in paths.items():
        if path in _list(values):
            return str(semantic)
    return None


def _snapshot_state(snapshot: Any, key: str) -> dict[str, Any]:
    if isinstance(snapshot, dict):
        value = snapshot.get(key, {})
        return value if isinstance(value, dict) else {}
    raw = getattr(snapshot, f"{key}_json", None)
    if isinstance(raw, str):
        import json
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}
    return {}


def _daily_usage(snapshots: Iterable[Any], date_value: Any) -> dict[str, float]:
    usage = {semantic: 0.0 for semantic in _RELATION_ALIASES}
    if date_value in (None, ""):
        return usage
    for snapshot in snapshots:
        before = project_card_variables(_snapshot_state(snapshot, "state_before"))
        after = project_card_variables(_snapshot_state(snapshot, "state_after"))
        if _dict(before.get("scene")).get("date") != date_value:
            continue
        before_relationship = _dict(before.get("relationship"))
        after_relationship = _dict(after.get("relationship"))
        for semantic in usage:
            old = before_relationship.get(semantic)
            new = after_relationship.get(semantic)
            if isinstance(old, (int, float)) and isinstance(new, (int, float)):
                usage[semantic] += abs(float(new) - float(old))
    return usage


def _locked(state: dict[str, Any], policy: dict[str, Any]) -> bool:
    lock = _dict(policy.get("terminal_lock"))
    if not lock.get("enabled"):
        return False
    relationship = _dict(project_card_variables(state).get("relationship"))
    return all(
        relationship.get(key) == lock.get(key)
        for key in ("affection", "fear", "dependence")
    )


def enforce_state_policy(
    state_before: dict[str, Any],
    operations: list[dict[str, Any]],
    policy: dict[str, Any] | None,
    previous_snapshots: Iterable[Any] = (),
) -> StatePolicyResult:
    """Enforce declared relationship limits for every update source.

    This runs after parsing but before the generic state engine. It therefore
    applies equally to primary MVU output, fallback extraction and future native
    retry actions.
    """

    policy = _dict(policy)
    if not policy.get("enabled"):
        return StatePolicyResult(copy.deepcopy(operations if isinstance(operations, list) else []))

    state_view = project_card_variables(state_before)
    relationship = _dict(state_view.get("relationship"))
    date_value = _dict(state_view.get("scene")).get("date")
    daily_used = _daily_usage(previous_snapshots, date_value)
    turn_used = {semantic: 0.0 for semantic in _RELATION_ALIASES}
    per_turn = policy.get("per_turn_absolute_limit")
    per_day = policy.get("per_day_absolute_limit")
    terminal_locked = _locked(state_before, policy)

    result = StatePolicyResult()
    for raw_operation in operations if isinstance(operations, list) else []:
        operation = copy.deepcopy(raw_operation)
        if not isinstance(operation, dict):
            result.rejected.append({"operation": operation, "error": "状态规则要求操作为对象"})
            continue
        path = str(operation.get("path", ""))
        op = str(operation.get("op", "")).lower()
        semantic = _semantic_for_path(path, policy)

        try:
            current_raw = _lookup(state_before, path)
        except (KeyError, IndexError, ValueError, TypeError):
            current_raw = None

        if op == "replace" and current_raw == operation.get("value"):
            result.rejected.append({"operation": operation, "error": "替换值与当前状态相同，已忽略无效操作"})
            continue
        if op == "append" and isinstance(current_raw, list) and operation.get("value") in current_raw:
            result.rejected.append({"operation": operation, "error": "数组已包含相同内容，已忽略重复记录"})
            continue

        if semantic is None or op not in {"increment", "delta", "replace"}:
            result.operations.append(operation)
            continue
        terminal_locked = terminal_locked or all(
            relationship.get(key) == _dict(policy.get("terminal_lock")).get(key)
            for key in ("affection", "fear", "dependence")
        )
        if terminal_locked and semantic in {"affection", "fear", "dependence"}:
            result.rejected.append({"operation": operation, "error": "角色卡终局状态已锁定，关系数值不再变化"})
            continue

        current = relationship.get(semantic)
        if not isinstance(current, (int, float)):
            result.operations.append(operation)
            continue
        if op in {"increment", "delta"}:
            raw_delta = operation.get("value")
            if not isinstance(raw_delta, (int, float)) or isinstance(raw_delta, bool):
                result.operations.append(operation)
                continue
            desired_delta = float(raw_delta)
        else:
            replacement = operation.get("value")
            if not isinstance(replacement, (int, float)) or isinstance(replacement, bool):
                result.operations.append(operation)
                continue
            desired_delta = float(replacement) - float(current)

        allowed_abs = abs(desired_delta)
        if isinstance(per_turn, (int, float)):
            allowed_abs = min(allowed_abs, max(0.0, float(per_turn) - turn_used[semantic]))
        if isinstance(per_day, (int, float)):
            allowed_abs = min(allowed_abs, max(0.0, float(per_day) - daily_used[semantic] - turn_used[semantic]))
        adjusted_delta = (1 if desired_delta >= 0 else -1) * allowed_abs

        # Respect numeric 0-100 bounds before handing the operation to the engine.
        target = max(0.0, min(100.0, float(current) + adjusted_delta))
        adjusted_delta = target - float(current)
        if abs(adjusted_delta) < 1e-9:
            result.rejected.append({"operation": operation, "error": "关系数值已达到边界或当日变化上限，操作未生效"})
            continue

        adjusted = copy.deepcopy(operation)
        if op in {"increment", "delta"}:
            adjusted["value"] = int(adjusted_delta) if adjusted_delta.is_integer() else adjusted_delta
        else:
            adjusted["value"] = int(target) if target.is_integer() else target
        result.operations.append(adjusted)
        turn_used[semantic] += abs(adjusted_delta)
        relationship[semantic] = target
        terminal_locked = terminal_locked or all(
            relationship.get(key) == _dict(policy.get("terminal_lock")).get(key)
            for key in ("affection", "fear", "dependence")
        )
        if adjusted != operation:
            result.adjusted.append({
                "operation": operation,
                "applied_as": adjusted,
                "reason": "按角色卡声明的每轮/每日关系变化上限调整",
            })

    return result
