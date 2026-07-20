from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InitialVariableResult:
    variables: dict[str, Any] = field(default_factory=dict)
    source: str = "none"
    warnings: list[str] = field(default_factory=list)


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return ""
    lower = value.lower()
    if lower in {"true", "yes", "on"}:
        return True
    if lower in {"false", "no", "off"}:
        return False
    if lower in {"null", "none", "~"}:
        return None
    if value in {"{}", "[]"}:
        return {} if value == "{}" else []
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        if value.startswith('"'):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        return value[1:-1].replace("\\'", "'")
    if re.fullmatch(r"[-+]?\d+", value):
        try:
            return int(value)
        except ValueError:
            pass
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][-+]?\d+)?", value):
        try:
            return float(value)
        except ValueError:
            pass
    if value.startswith(("{", "[")):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value


def _split_mapping(line: str) -> tuple[str, str] | None:
    quote: str | None = None
    depth = 0
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
            continue
        if char in "[{(":
            depth += 1
            continue
        if char in "]})":
            depth = max(0, depth - 1)
            continue
        if char in {":", "："} and depth == 0:
            return line[:index].strip(), line[index + 1 :].strip()
    return None


def parse_yaml_mapping_subset(text: str) -> dict[str, Any]:
    """Parse the mapping-oriented YAML subset commonly used by `[initvar]` entries.

    It intentionally supports nested mappings and scalar/inline JSON values only. It
    does not implement tags, anchors, code execution, object constructors, or other
    YAML features that would be unsafe for an imported character card.
    """

    cleaned = (text or "").replace("\t", "  ").strip()
    cleaned = re.sub(r"^```(?:ya?ml)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for line_number, raw_line in enumerate(cleaned.splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        body = raw_line.strip()
        mapping = _split_mapping(body)
        if mapping is None:
            raise ValueError(f"第 {line_number} 行不是受支持的键值结构")
        key, raw_value = mapping
        if not key:
            raise ValueError(f"第 {line_number} 行缺少字段名")
        if key in {"__proto__", "prototype", "constructor"} or key.startswith("_"):
            raise ValueError(f"第 {line_number} 行包含禁止字段")

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if raw_value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(raw_value)

    return root


def _initvar_entries(normalized: dict) -> list[dict]:
    book = _dict(normalized.get("character_book"))
    entries = _list(book.get("entries"))
    result: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        comment = str(entry.get("comment", "")).strip().lower().replace(" ", "")
        if comment in {"[initvar]", "initvar", "[初始化变量]", "初始化变量", "[初始变量]", "初始变量"}:
            result.append(entry)
    return result


def _parse_initvar_content(content: str) -> dict[str, Any]:
    """Parse the two common Tavern init-variable encodings safely."""
    text = str(content or "").strip()
    if not text:
        return {}
    fenced = re.fullmatch(r"```(?:json|yaml|yml)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    if text.startswith("{"):
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("[initvar] JSON 根节点必须是对象")
        return payload
    return parse_yaml_mapping_subset(text)


def extract_card_variables(normalized: dict) -> InitialVariableResult:
    normalized = normalized if isinstance(normalized, dict) else {}
    extensions = _dict(normalized.get("extensions"))
    helper = _dict(extensions.get("tavern_helper"))
    helper_variables = _dict(helper.get("variables"))

    stat_data = helper_variables.get("stat_data")
    if isinstance(stat_data, dict) and stat_data:
        return InitialVariableResult(copy.deepcopy(stat_data), "tavern_helper.variables.stat_data")
    if helper_variables:
        return InitialVariableResult(copy.deepcopy(helper_variables), "tavern_helper.variables")

    warnings: list[str] = []
    for entry in _initvar_entries(normalized):
        content = str(entry.get("content", "")).strip()
        if not content:
            continue
        try:
            variables = _parse_initvar_content(content)
        except (ValueError, json.JSONDecodeError) as error:
            warnings.append(f"[initvar] 解析失败: {error}")
            continue
        if variables:
            return InitialVariableResult(variables, "worldbook:[initvar]", warnings)

    return InitialVariableResult({}, "none", warnings)


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    for key, value in source.items():
        if key in {"__proto__", "prototype", "constructor"} or str(key).startswith("_"):
            continue
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def merge_card_variables(base_state: dict, variables: dict) -> dict:
    result = copy.deepcopy(base_state if isinstance(base_state, dict) else {})
    custom = result.get("custom")
    if not isinstance(custom, dict):
        custom = {}
        result["custom"] = custom
    if isinstance(variables, dict):
        _deep_merge(custom, variables)
    return project_card_variables(result)


def _deep_fill_missing(target: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    for key, value in defaults.items():
        if key in {"__proto__", "prototype", "constructor"} or str(key).startswith("_"):
            continue
        if key not in target:
            target[key] = copy.deepcopy(value)
        elif isinstance(target.get(key), dict) and isinstance(value, dict):
            _deep_fill_missing(target[key], value)
    return target


def backfill_card_variables(existing_state: dict, variables: dict) -> dict:
    """Add newly understood card defaults without overwriting played progress."""
    result = copy.deepcopy(existing_state if isinstance(existing_state, dict) else {})
    custom = result.get("custom")
    if not isinstance(custom, dict):
        custom = {}
        result["custom"] = custom
    if isinstance(variables, dict):
        _deep_fill_missing(custom, variables)
    return project_card_variables(result)

_WORLD_ROOT_ALIASES = {
    "世界信息", "世界状态", "环境信息", "场景信息",
    "world", "world_info", "worldinfo", "world_state", "scene", "scene_state",
}


def _case_get(source: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        if alias in source:
            return source[alias]
        lowered = alias.lower()
        for key, value in source.items():
            if str(key).lower() == lowered:
                return value
    return None


def _put_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None and value != "":
        target[key] = copy.deepcopy(value)


def _clean_projected_value(value: Any) -> Any:
    """Remove MVU schema markers from player-facing projections only.

    The complete card-owned structure remains untouched under ``custom`` so
    future MVU commands can continue addressing its original paths.
    """
    if isinstance(value, list):
        return [
            _clean_projected_value(item)
            for item in value
            if item != "$__META_EXTENSIBLE__$"
        ]
    if isinstance(value, dict):
        return {
            str(key): _clean_projected_value(item)
            for key, item in value.items()
            if str(key) != "$meta" and item != "$__META_EXTENSIBLE__$"
        }
    return copy.deepcopy(value)


def _mvu_value(value: Any) -> Any:
    if isinstance(value, list) and len(value) == 2 and isinstance(value[1], str):
        return _clean_projected_value(value[0])
    return _clean_projected_value(value)


def project_card_variables(state: dict) -> dict:
    """Project common card variable names into player-facing runtime sections.

    The complete source data remains under ``custom``. This projection is a
    generic alias layer, not a schema tied to any card or language.
    """
    result = copy.deepcopy(state if isinstance(state, dict) else {})
    custom = result.get("custom")
    if not isinstance(custom, dict):
        return result

    had_scene = isinstance(result.get("scene"), dict)
    had_relationship = isinstance(result.get("relationship"), dict)
    had_character = isinstance(result.get("character"), dict)
    scene = copy.deepcopy(result.get("scene")) if had_scene else {}
    relationship = copy.deepcopy(result.get("relationship")) if had_relationship else {}
    character = copy.deepcopy(result.get("character")) if had_character else {}

    world: dict[str, Any] | None = None
    for root_name, value in custom.items():
        if isinstance(value, dict) and (str(root_name) in _WORLD_ROOT_ALIASES or str(root_name).lower() in _WORLD_ROOT_ALIASES):
            world = value
            break
    if world:
        _put_if_present(scene, "location", _mvu_value(_case_get(world, ("当前地点", "地点", "位置", "location", "place"))))
        _put_if_present(scene, "time", _mvu_value(_case_get(world, ("当前时间", "时间", "日期时间", "time", "datetime"))))
        _put_if_present(scene, "date", _mvu_value(_case_get(world, ("日期", "当前日期", "date"))))
        _put_if_present(scene, "weather", _mvu_value(_case_get(world, ("天气", "weather"))))
        _put_if_present(scene, "atmosphere", _mvu_value(_case_get(world, ("氛围", "气氛", "环境", "atmosphere"))))
        _put_if_present(scene, "objective", _mvu_value(_case_get(world, ("当前目标", "目标", "objective"))))
        relation_value = _case_get(world, ("主角与角色的关系", "主角关系", "关系阶段", "relationship", "relation"))
        if relation_value in (None, ""):
            for key, value in world.items():
                if "关系" in str(key) and not isinstance(value, (dict, list)):
                    relation_value = value
                    break
        _put_if_present(relationship, "stage", _mvu_value(relation_value))

    primary_name = str(character.get("name", "")).strip()
    primary: dict[str, Any] | None = None
    if primary_name and isinstance(custom.get(primary_name), dict):
        primary = custom[primary_name]
    if primary is None:
        for root_name, value in custom.items():
            if not isinstance(value, dict):
                continue
            if str(root_name) in _WORLD_ROOT_ALIASES or str(root_name).lower() in _WORLD_ROOT_ALIASES:
                continue
            keys = {str(key).lower() for key in value}
            if keys.intersection({"好感度", "好感", "affection", "favorability", "当前状态", "情绪强度", "mood"}):
                primary = value
                break

    if primary:
        _put_if_present(relationship, "affection", _mvu_value(_case_get(primary, ("好感度", "好感", "affection", "favorability", "affinity"))))
        _put_if_present(relationship, "trust", _mvu_value(_case_get(primary, ("信任度", "信任", "trust"))))
        _put_if_present(relationship, "tension", _mvu_value(_case_get(primary, ("张力", "tension"))))
        _put_if_present(relationship, "intimacy", _mvu_value(_case_get(primary, ("亲密度", "亲密", "intimacy"))))
        _put_if_present(relationship, "fear", _mvu_value(_case_get(primary, ("害怕值", "恐惧值", "畏惧", "fear"))))
        _put_if_present(relationship, "dependence", _mvu_value(_case_get(primary, ("依赖值", "依赖度", "dependence", "dependency"))))
        _put_if_present(character, "state", _mvu_value(_case_get(primary, ("当前状态", "状态", "state", "form"))))
        _put_if_present(character, "mood", _mvu_value(_case_get(primary, ("当前情绪", "情绪", "mood", "emotion"))))
        _put_if_present(character, "emotion_intensity", _mvu_value(_case_get(primary, ("情绪强度", "emotion_intensity", "emotionIntensity"))))
        _put_if_present(character, "expression", _mvu_value(_case_get(primary, ("表情", "expression"))))
        _put_if_present(character, "outfit", _mvu_value(_case_get(primary, ("服装", "衣着", "outfit"))))
        _put_if_present(character, "injuries", _mvu_value(_case_get(primary, ("身上的伤", "伤势", "伤口", "injuries"))))
        _put_if_present(character, "important_memories", _mvu_value(_case_get(primary, ("重要记忆", "关键记忆", "important_memories"))))

    if had_scene or scene:
        result["scene"] = scene
    else:
        result.pop("scene", None)
    if had_relationship or relationship:
        result["relationship"] = relationship
    else:
        result.pop("relationship", None)
    if had_character or character:
        result["character"] = character
    else:
        result.pop("character", None)

    return result
