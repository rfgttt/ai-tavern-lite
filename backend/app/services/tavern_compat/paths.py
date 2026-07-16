from __future__ import annotations

from typing import Any


CANONICAL_ROOT_ALIASES = {
    "scene": "scene",
    "场景": "scene",
    "环境": "scene",
    "当前场景": "scene",
    "relationship": "relationship",
    "relation": "relationship",
    "关系": "relationship",
    "人际关系": "relationship",
    "关系状态": "relationship",
    "quests": "quests",
    "quest": "quests",
    "tasks": "quests",
    "task": "quests",
    "任务": "quests",
    "任务列表": "quests",
    "目标列表": "quests",
    "inventory": "inventory",
    "items": "inventory",
    "item": "inventory",
    "背包": "inventory",
    "物品": "inventory",
    "道具": "inventory",
    "combat": "combat",
    "battle": "combat",
    "战斗": "combat",
    "战斗状态": "combat",
    "character": "character",
    "char": "character",
    "角色": "character",
    "角色状态": "character",
    "player": "player",
    "user": "player",
    "玩家": "player",
    "玩家状态": "player",
}

_VARIABLE_CONTAINER_ROOTS = {
    "stat_data",
    "variables",
    "variable",
    "vars",
    "状态数据",
    "变量",
}


def _decode(part: str) -> str:
    return part.replace("~1", "/").replace("~0", "~")


def _alias(part: str) -> str | None:
    decoded = _decode(part)
    return CANONICAL_ROOT_ALIASES.get(decoded.lower(), CANONICAL_ROOT_ALIASES.get(decoded))


def normalize_card_pointer(path: Any) -> str:
    """Map card-owned JSON pointers into the stable runtime namespace.

    Platform roots remain canonical. Tavern/MVU variable containers are stripped,
    and every unknown root is stored below `/custom` so imported cards cannot
    overwrite platform metadata or create arbitrary top-level state branches.
    """

    text = str(path or "").strip()
    if not text.startswith("/"):
        return text
    if text == "/":
        return text

    parts = text[1:].split("/")
    if not parts:
        return text

    decoded_root = _decode(parts[0])
    if decoded_root.lower() in _VARIABLE_CONTAINER_ROOTS or decoded_root in _VARIABLE_CONTAINER_ROOTS:
        remainder = parts[1:]
        return "/custom" + ("/" + "/".join(remainder) if remainder else "")

    if decoded_root == "custom":
        if len(parts) >= 2:
            alias = _alias(parts[1])
            if alias:
                return "/" + "/".join([alias, *parts[2:]])
        return text

    alias = _alias(parts[0])
    if alias:
        return "/" + "/".join([alias, *parts[1:]])

    return "/custom/" + "/".join(parts)
