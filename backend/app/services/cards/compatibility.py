from __future__ import annotations

import json
import re
from typing import Any

from ..tavern_compat.initial_state import extract_card_variables

KNOWN_EXTENSIONS = {
    "talkativeness",
    "fav",
    "world",
    "depth_prompt",
    "regex_scripts",
    "tavern_helper",
    "ai_tavern_runtime",
    "ai_tavern_ui",
    "group_only_greetings",
}


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _all_entries(normalized: dict) -> list[dict]:
    entries = _list(_dict(normalized.get("character_book")).get("entries"))
    return [item for item in entries if isinstance(item, dict)]


def _enabled_entries(normalized: dict) -> list[dict]:
    return [item for item in _all_entries(normalized) if item.get("enabled", True)]


def _active_regex_scripts(extensions: dict) -> list[dict]:
    scripts = _list(extensions.get("regex_scripts"))
    return [item for item in scripts if isinstance(item, dict) and not item.get("disabled", False)]


def _helper_scripts(extensions: dict) -> list[dict]:
    scripts = _list(_dict(extensions.get("tavern_helper")).get("scripts"))
    return [item for item in scripts if isinstance(item, dict) and item.get("enabled", True)]


def _metadata(normalized: dict, entries: list[dict], regex_scripts: list[dict], helper_scripts: list[dict]) -> str:
    pieces = [
        str(normalized.get("name", "")),
        str(normalized.get("description", "")),
        str(normalized.get("scenario", "")),
        str(normalized.get("first_mes", "")),
    ]
    for entry in entries:
        pieces.append(str(entry.get("comment", "")))
        pieces.extend(str(key) for key in _list(entry.get("keys")))
        pieces.append(str(entry.get("content", ""))[:4000])
    for script in regex_scripts:
        pieces.append(str(script.get("scriptName", script.get("name", ""))))
        pieces.append(str(script.get("findRegex", "")))
        pieces.append(str(script.get("replaceString", ""))[:1000])
    for script in helper_scripts:
        pieces.append(str(script.get("name", "")))
        pieces.append(str(script.get("info", "")))
        pieces.append(str(script.get("content", ""))[:2000])
    return "\n".join(pieces).lower()


def build_compatibility_report(normalized: dict) -> dict:
    """Analyze card protocols and the safe runtime's actual ability to use them."""
    normalized = normalized if isinstance(normalized, dict) else {}
    extensions = _dict(normalized.get("extensions"))
    all_entries = _all_entries(normalized)
    entries = _enabled_entries(normalized)
    regex_scripts = _active_regex_scripts(extensions)
    helper_scripts = _helper_scripts(extensions)
    metadata = _metadata(normalized, entries, regex_scripts, helper_scripts)
    ui_manifest = _dict(extensions.get("ai_tavern_ui"))
    assets = _list(normalized.get("assets"))
    initial = extract_card_variables(normalized)

    capabilities = {
        "worldbook": bool(entries),
        "alternate_greetings": bool(_list(normalized.get("alternate_greetings"))),
        "regex": bool(regex_scripts),
        "mvu": any(term in metadata for term in ("updatevariable", "update_variable", "jsonpatch", "mvu", "变量更新")),
        "dice": bool(re.search(r"<dice\b|掷骰|骰子", metadata, re.IGNORECASE)),
        "battle_check": bool(re.search(r"battlecheck|战斗检定", metadata, re.IGNORECASE)),
        "battle": bool(re.search(r"<battle\b|战斗面板|tactical map", metadata, re.IGNORECASE)),
        "status_panel": any(term in metadata for term in ("statusplaceholder", "状态栏", "角色面板")),
        "ui_manifest": ui_manifest.get("schema") == "ai-tavern-ui/1",
        "assets": bool(assets),
        "group_greetings": bool(_list(normalized.get("group_only_greetings"))),
        "scene_state": bool(str(normalized.get("scenario", "")).strip()) or any(
            term in metadata for term in ("场景变量", "当前地点", "location", "scene state", "环境状态")
        ),
        "relationship_state": any(
            term in metadata
            for term in ("好感度", "信任度", "亲密度", "关系值", "关系变量", "relationship", "affection", "tension")
        ),
        "quest_state": any(term in metadata for term in ("任务变量", "任务列表", "quest state", "任务进度")),
        "inventory_state": any(term in metadata for term in ("背包变量", "物品列表", "inventory state", "道具栏", "特殊物品")),
    }

    has_read_only_macros = any(term in metadata for term in (
        "{{getvar::", "{{format_message_variable::", "<user>", "<char>", "{{user}}", "{{char}}",
    ))
    has_ejs = "<%" in metadata
    has_getwi = "getwi(" in metadata
    external_js = any(re.search(r"https?://", str(script.get("content", "")), re.IGNORECASE) for script in helper_scripts)

    runtime_checks = {
        "initial_variables": {
            "status": "supported" if initial.variables else "absent",
            "source": initial.source,
            "summary": (
                f"已从 {initial.source} 初始化 {len(initial.variables)} 个顶层变量"
                if initial.variables else "未找到 Tavern Helper variables 或 [initvar] 初始变量"
            ),
            "warnings": initial.warnings,
        },
        "patch_paths": {
            "status": "supported" if capabilities["mvu"] else "absent",
            "summary": "未知 MVU 根路径会安全映射到 /custom，支持 replace/add/remove 等状态操作" if capabilities["mvu"] else "未检测到变量更新协议",
        },
        "read_only_macros": {
            "status": "supported" if has_read_only_macros else "absent",
            "summary": "支持 user/char、getvar 和 stat_data 格式化宏" if has_read_only_macros else "未检测到可读宏",
        },
        "dynamic_templates": {
            "status": "partial" if has_ejs else "absent",
            "summary": (
                "支持常见 getvar + 数值条件 + getwi 只读选择；其他 EJS/STscript 不执行"
                if has_ejs else "未检测到 EJS 模板"
            ),
        },
        "status_placeholder": {
            "status": "supported" if capabilities["status_panel"] else "absent",
            "summary": "状态占位符会转换为原生安全状态栏" if capabilities["status_panel"] else "未检测到状态栏占位符",
        },
        "external_javascript": {
            "status": "isolated" if external_js or helper_scripts else "absent",
            "summary": "外部脚本与任意 Tavern Helper JavaScript 被隔离，不会加载或执行" if external_js or helper_scripts else "未检测到外部脚本",
        },
    }

    unknown_extensions = sorted(key for key in extensions.keys() if key not in KNOWN_EXTENSIONS)
    warnings: list[str] = []
    unsupported: list[str] = []
    if regex_scripts:
        warnings.append("Regex 的隐藏/占位协议可兼容；任意 HTML、CSS 脚本不会直接进入主页面。")
    if helper_scripts:
        warnings.append("Tavern Helper 采用安全兼容子集，不执行任意 JavaScript。")
        unsupported.append("arbitrary_tavern_helper_javascript")
    if has_ejs:
        warnings.append("EJS 仅解释只读变量条件与 getwi 选择；复杂代码会被移除。")
        unsupported.append("arbitrary_ejs_javascript")
    if external_js:
        unsupported.append("external_javascript_imports")
    warnings.extend(initial.warnings)

    def detail(key: str, label: str, status: str, summary: str) -> dict:
        return {"key": key, "label": label, "status": status, "summary": summary}

    if capabilities["mvu"]:
        mvu_status = "supported" if initial.variables else "partial"
        mvu_summary = (
            f"变量协议已识别，并通过 {initial.source} 完成初始化"
            if initial.variables else "更新协议已识别，但缺少可用初始变量；replace 路径可能被拒绝"
        )
    else:
        mvu_status = "absent"
        mvu_summary = "未检测到 MVU 变量协议"

    details = [
        detail(
            "worldbook", "世界书", "supported" if capabilities["worldbook"] else "absent",
            f"已识别 {len(entries)} 条启用条目；另保留 {len(all_entries) - len(entries)} 条关闭条目用于 initvar/getwi" if all_entries else "角色卡未包含世界书条目",
        ),
        detail(
            "regex", "Regex 显示规则", "partial" if regex_scripts else "absent",
            f"发现 {len(regex_scripts)} 条；隐藏变量与状态占位可转换，任意 HTML/脚本已隔离" if regex_scripts else "未发现 Regex 规则",
        ),
        detail("mvu", "MVU / 变量更新", mvu_status, mvu_summary),
        detail(
            "macros", "酒馆宏", "supported" if has_read_only_macros else "absent",
            "支持身份、只读变量和 stat_data 格式化；复杂脚本宏仅部分兼容" if has_read_only_macros else "未检测到酒馆宏",
        ),
        detail(
            "status_panel", "角色卡状态栏", "supported" if capabilities["status_panel"] else "absent",
            "检测到状态栏声明；将占位符转换为原生安全面板" if capabilities["status_panel"] else "未检测到角色卡状态栏",
        ),
        detail(
            "relationship_state", "关系变量", "supported" if capabilities["relationship_state"] and initial.variables else "partial" if capabilities["relationship_state"] else "absent",
            "检测到角色卡原生关系字段并可从初始变量展示" if capabilities["relationship_state"] and initial.variables else "检测到关系字段，但尚无可靠初始化" if capabilities["relationship_state"] else "未声明关系变量",
        ),
        detail(
            "scene_state", "场景状态", "supported" if capabilities["scene_state"] else "absent",
            "可从角色卡场景或变量建立当前场景" if capabilities["scene_state"] else "尚无可识别的场景状态",
        ),
        detail(
            "dice", "骰子组件", "supported" if capabilities["dice"] else "absent",
            "可转换为原生骰子卡" if capabilities["dice"] else "未检测到骰子协议",
        ),
        detail(
            "battle", "战斗组件", "supported" if capabilities["battle"] or capabilities["battle_check"] else "absent",
            "可转换战斗检定或战斗快照" if capabilities["battle"] or capabilities["battle_check"] else "未检测到战斗协议",
        ),
    ]

    native = ["generic-state", "message-ast", "state-diff"]
    if capabilities["status_panel"]:
        native.append("inline-card-state")
    for key, renderer in (
        ("dice", "dice"),
        ("battle_check", "battle-check"),
        ("battle", "battle-map"),
        ("ui_manifest", "manifest"),
    ):
        if capabilities[key]:
            native.append(renderer)

    return {
        "version": 3,
        "compatibility_core": "tavern-safe-v2",
        "card_format": str(normalized.get("spec", "chara_card_v2")),
        "card_format_version": str(normalized.get("spec_version", "2.0")),
        "capabilities": capabilities,
        "details": details,
        "runtime_checks": runtime_checks,
        "counts": {
            "enabled_lorebook_entries": len(entries),
            "disabled_lorebook_entries": len(all_entries) - len(entries),
            "active_regex_scripts": len(regex_scripts),
            "helper_scripts": len(helper_scripts),
            "assets": len(assets),
            "alternate_greetings": len(_list(normalized.get("alternate_greetings"))),
            "initial_variable_roots": len(initial.variables),
        },
        "native_renderers": native,
        "unknown_extensions": unknown_extensions,
        "ui_manifest": ui_manifest if capabilities["ui_manifest"] else None,
        "warnings": warnings,
        "unsupported": sorted(set(unsupported)),
        "script_execution": "safe-subset-only",
    }
