from __future__ import annotations

import re
from typing import Any

from ..tavern_compat.initial_state import extract_card_variables, project_card_variables
from ..tavern_compat.emulation import extract_safe_emulation
from .state_policy import extract_state_policy
from .state_schema import build_state_schema
from .state_aliases import build_alias_registry


_DND_HINTS = (
    "d&d",
    "dnd",
    "龙与地下城",
    "先攻",
    "护甲等级",
    "法术位",
)


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _enabled_worldbook_entries(normalized: dict) -> list[dict]:
    book = _as_dict(normalized.get("character_book"))
    entries = _as_list(book.get("entries"))
    return [entry for entry in entries if isinstance(entry, dict) and entry.get("enabled", True)]


def _active_regex_scripts(normalized: dict) -> list[dict]:
    extensions = _as_dict(normalized.get("extensions"))
    scripts = _as_list(extensions.get("regex_scripts"))
    return [script for script in scripts if isinstance(script, dict) and not script.get("disabled", False)]


def _metadata_text(normalized: dict, enabled_entries: list[dict], scripts: list[dict]) -> str:
    """Collect only names, keys and matching patterns; never execute or ingest replacement code."""
    extensions = _as_dict(normalized.get("extensions"))
    helper = _as_dict(extensions.get("tavern_helper"))
    helper_scripts = _as_list(helper.get("scripts"))

    pieces: list[str] = [
        str(normalized.get("name", "")),
        str(normalized.get("description", "")),
        str(normalized.get("scenario", "")),
        str(extensions.get("world", "")),
        " ".join(str(tag) for tag in _as_list(normalized.get("tags"))),
    ]
    for entry in enabled_entries:
        pieces.append(str(entry.get("comment", "")))
        pieces.extend(str(key) for key in _as_list(entry.get("keys")))
        # A short prefix is enough to recognize text protocols. Disabled entries are never read.
        pieces.append(str(entry.get("content", ""))[:320])
    for script in scripts:
        pieces.append(str(script.get("scriptName", script.get("name", ""))))
        pieces.append(str(script.get("findRegex", "")))
    for script in helper_scripts:
        if isinstance(script, dict) and script.get("enabled", True):
            pieces.append(str(script.get("name", "")))
            pieces.append(str(script.get("info", "")))
            pieces.append(str(script.get("content", ""))[:240])
    return "\n".join(pieces).lower()


def analyze_card(normalized: dict) -> dict:
    """Describe supported card capabilities without executing card-provided scripts."""
    normalized = normalized if isinstance(normalized, dict) else {}
    enabled_entries = _enabled_worldbook_entries(normalized)
    scripts = _active_regex_scripts(normalized)
    initial_variables = extract_card_variables(normalized)
    metadata = _metadata_text(normalized, enabled_entries, scripts)
    if initial_variables.variables:
        metadata += "\n" + str(initial_variables.variables).lower()

    enabled_protocol_text = "\n".join(str(entry.get("content", "")) for entry in enabled_entries).lower()
    mvu_command_protocol = bool(re.search(r"_\.(?:set|add|insert|remove)\s*\(", enabled_protocol_text))
    mvu_json_patch_protocol = "jsonpatch" in enabled_protocol_text
    text_status_protocol = bool(
        re.search(r"<\s*text(?:\s[^>]*)?>.*?<\s*end\s*>", metadata, flags=re.IGNORECASE | re.DOTALL)
        or re.search(r"<\s*status(?:\s[^>]*)?>.*?<\s*/\s*status\s*>", metadata, flags=re.IGNORECASE | re.DOTALL)
        or ("[环境]" in metadata and ("[角色状态" in metadata or "[人物状态" in metadata))
    )

    capabilities = {
        "worldbook": bool(enabled_entries),
        "alternate_greetings": bool(_as_list(normalized.get("alternate_greetings"))),
        "mvu_state": any(
            hint in metadata
            for hint in ("updatevariable", "update_variable", "jsonpatch", "mvu", "变量更新", "变量结构")
        ),
        "mvu_command_protocol": mvu_command_protocol,
        "mvu_json_patch_protocol": mvu_json_patch_protocol,
        "dice": bool(re.search(r"<dice\b|骰子|掷骰", metadata, flags=re.IGNORECASE)),
        "battle_check": bool(re.search(r"battlecheck|战斗检定", metadata, flags=re.IGNORECASE)),
        "battle": bool(re.search(r"<battle\b|战斗面板|tactical map", metadata, flags=re.IGNORECASE)),
        "status_placeholder": "statusplaceholder" in metadata,
        "text_status_protocol": text_status_protocol,
        "scene_state": bool(str(normalized.get("scenario", "")).strip()) or any(
            term in metadata for term in ("场景变量", "当前地点", "location", "scene state", "环境状态")
        ),
        "relationship_state": any(
            term in metadata
            for term in (
                "好感度", "信任度", "亲密度", "关系值", "关系变量",
                "relationship", "affection", "tension", "attitude score",
            )
        ),
        "quest_state": any(term in metadata for term in ("任务变量", "任务列表", "quest state", "任务进度")),
        "inventory_state": any(term in metadata for term in ("背包变量", "物品列表", "inventory state", "道具栏")),
    }

    if initial_variables.variables:
        projected = project_card_variables({
            "scene": {},
            "relationship": {},
            "character": {"name": str(normalized.get("name", ""))},
            "custom": initial_variables.variables,
        })
        capabilities["scene_state"] = capabilities["scene_state"] or bool(_as_dict(projected.get("scene")))

    dnd_score = sum(hint in metadata for hint in _DND_HINTS)
    if capabilities["battle"] or capabilities["dice"] or dnd_score >= 2:
        mode = "adventure"
    elif capabilities["relationship_state"]:
        mode = "relationship"
    else:
        # Plain conversational cards use the relationship-friendly runtime shell.
        # Capability flags still describe whether the card provides its own relationship protocol.
        mode = "relationship"

    native_renderers = ["state"]
    if capabilities["text_status_protocol"]:
        native_renderers.append("text_status")
    if capabilities["dice"]:
        native_renderers.append("dice")
    if capabilities["battle_check"] or capabilities["battle"]:
        native_renderers.append("battle_check")
    if capabilities["battle"]:
        native_renderers.append("battle_map")

    first_message = str(normalized.get("first_mes", ""))
    visible_urls = re.findall(r"https?://[^\s'\"<>]+", first_message)
    extensions = _as_dict(normalized.get("extensions"))
    emulation = _as_dict(extensions.get("ai_tavern_emulation")) or extract_safe_emulation(normalized)
    state_policy = extract_state_policy(normalized)
    recommended_context_window = int(state_policy.get("recommended_context_window", 8192) or 8192)
    capabilities["formal_state_schema"] = True
    capabilities["card_scoped_aliases"] = True

    profile = {
        "version": 8,
        "compatibility_core": "tavern-safe-v6",
        "mode": mode,
        "card_spec": str(normalized.get("spec", "chara_card_v2")),
        "card_spec_version": str(normalized.get("spec_version", "2.0")),
        "capabilities": capabilities,
        "native_renderers": native_renderers,
        "script_execution": "safe-native-emulation" if emulation else "disabled",
        "emulation": emulation,
        "state_policy": state_policy,
        "recommended_context_window": recommended_context_window,
        "regex_script_count": len(scripts) or int(_as_dict(emulation.get("source")).get("regex_script_count", 0) or 0),
        "lorebook_entry_count": len(enabled_entries),
        "external_resource_count": len(set(visible_urls)),
        "initial_variable_source": initial_variables.source,
        "initial_variable_roots": len(initial_variables.variables),
        "warnings": initial_variables.warnings + ([
            "角色卡脚本不会直接执行；已识别的状态栏、提示词隐藏和按钮意图会由原生安全组件等价实现。"
        ] if scripts or emulation else []) + ([
            "检测到文本状态栏协议；状态块将作为纯文本解析并由原生组件展示，不执行卡片 HTML 或 JavaScript。"
        ] if text_status_protocol else []) + ([
            f"该角色卡建议上下文窗口至少为 {recommended_context_window}。"
        ] if recommended_context_window > 8192 else []),
    }

    # Build the schema from the same initial state users will receive. The
    # import is local so the runtime state engine remains independent from card
    # analysis and no card-provided code is evaluated.
    from .state_engine import build_initial_state

    initial_state = build_initial_state(profile, normalized)
    profile["state_schema"] = build_state_schema(initial_state, policy=state_policy)
    profile["state_schema_summary"] = profile["state_schema"].get("summary", {})
    profile["state_aliases"] = build_alias_registry(profile["state_schema"])
    profile["state_alias_summary"] = profile["state_aliases"].get("summary", {})
    return profile
