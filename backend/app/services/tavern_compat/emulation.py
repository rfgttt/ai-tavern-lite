from __future__ import annotations

import re
from typing import Any


_STATUS_PLACEHOLDER_RE = re.compile(r"<StatusPlaceHolderImpl\s*/>", re.IGNORECASE)
_UPDATE_VARIABLE_RE = re.compile(
    r"<UpdateVariable(?:variable)?\b[^>]*>[\s\S]*?</UpdateVariable(?:variable)?>",
    re.IGNORECASE,
)
_ANALYSIS_RE = re.compile(r"<Analysis\b[^>]*>[\s\S]*?</Analysis>", re.IGNORECASE)
_UNCLOSED_UPDATE_RE = re.compile(
    r"<UpdateVariable(?:variable)?\b[^>]*>[\s\S]*$",
    re.IGNORECASE,
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _active_regex_scripts(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    extensions = _dict(normalized.get("extensions"))
    return [
        item
        for item in _list(extensions.get("regex_scripts"))
        if isinstance(item, dict) and not item.get("disabled", False)
    ]


def _helper_scripts(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    extensions = _dict(normalized.get("extensions"))
    raw_helper = extensions.get("tavern_helper")
    helper = _dict(raw_helper)
    if isinstance(raw_helper, list):
        helper = {
            str(item[0]): item[1]
            for item in raw_helper
            if isinstance(item, list) and len(item) == 2
        }
    scripts = helper.get("scripts")
    if isinstance(scripts, dict):
        scripts = scripts.get("scripts")
    return [
        item
        for item in _list(scripts)
        if isinstance(item, dict) and item.get("enabled", True)
    ]


def _native_action(label: str) -> dict[str, str] | None:
    compact = re.sub(r"\s+", "", str(label or ""))
    mapping = {
        "重新处理变量": ("reprocess_variables", "重新处理变量", "automatic"),
        "重新读取初始变量": ("restore_initial_state", "重新读取初始变量", "supported"),
        "清除旧楼层变量": ("clear_old_turn_state", "清除旧楼层变量", "native_timeline"),
        "快照楼层": ("snapshot_turn", "快照楼层", "native_timeline"),
        "重演楼层": ("replay_turn", "重演楼层", "native_timeline"),
        "重试额外模型解析": ("retry_state_extractor", "重试额外模型解析", "planned"),
    }
    value = mapping.get(compact)
    if value is None:
        return None
    action_id, action_label, status = value
    return {"id": action_id, "label": action_label, "status": status}


def extract_safe_emulation(normalized: dict[str, Any]) -> dict[str, Any]:
    """Convert executable card extensions into a declarative, non-executable manifest.

    Only capability names and presentation hints are retained. Regex replacement
    source, JavaScript source, external URLs and event handlers are never copied.
    """

    normalized = normalized if isinstance(normalized, dict) else {}
    regex_scripts = _active_regex_scripts(normalized)
    helper_scripts = _helper_scripts(normalized)

    prompt_filters = {
        "status_placeholder": False,
        "update_variable": False,
        "analysis": False,
    }
    status_panel = False
    memory_pagination = False
    theme = "native"

    for script in regex_scripts:
        name = str(script.get("scriptName", script.get("name", "")))
        pattern = str(script.get("findRegex", ""))
        replacement = str(script.get("replaceString", ""))
        metadata = f"{name}\n{pattern}\n{replacement[:12000]}".lower()
        prompt_only = bool(script.get("promptOnly", False))

        if "statusplaceholderimpl" in metadata:
            prompt_filters["status_placeholder"] = prompt_filters["status_placeholder"] or prompt_only
            if any(token in metadata for token in ("status-container", "状态栏", "好感度", "害怕值")):
                status_panel = True
        if "updatevariable" in metadata:
            prompt_filters["update_variable"] = prompt_filters["update_variable"] or prompt_only
        if "<analysis" in metadata or "analysis>" in metadata:
            prompt_filters["analysis"] = prompt_filters["analysis"] or prompt_only
        if any(token in metadata for token in ("memory-pagination", "重要记忆", "上一页", "下一页")):
            memory_pagination = True
        if any(token in metadata for token in ("night-sky", "夜空", "moonlight", "月圆", "明月")):
            theme = "night_sky"

    actions: list[dict[str, str]] = []
    seen_actions: set[str] = set()
    for helper_script in helper_scripts:
        button = _dict(helper_script.get("button"))
        for raw_button in _list(button.get("buttons")):
            if not isinstance(raw_button, dict) or not raw_button.get("visible", False):
                continue
            action = _native_action(str(raw_button.get("name", "")))
            if action and action["id"] not in seen_actions:
                seen_actions.add(action["id"])
                actions.append(action)

    enabled = bool(regex_scripts or helper_scripts or status_panel or any(prompt_filters.values()))
    if not enabled:
        return {}

    return {
        "version": 1,
        "mode": "safe_native_emulation",
        "source": {
            "regex_script_count": len(regex_scripts),
            "helper_script_count": len(helper_scripts),
        },
        "prompt_filters": prompt_filters,
        "status_panel": {
            "enabled": status_panel,
            "theme": theme,
            "sections": ["scene", "relationship", "injuries", "important_memories"],
            "memory_page_size": 1 if memory_pagination else 5,
        },
        "native_actions": actions,
        "guarantees": [
            "不执行角色卡 JavaScript",
            "不加载角色卡外部网址",
            "不复制角色卡 HTML 事件处理器",
            "只保留可验证的声明式显示与操作意图",
        ],
    }


def sanitize_history_content(text: str, manifest: dict[str, Any] | None = None) -> str:
    """Remove card-only protocol/UI blocks before historical text reaches the model."""

    value = str(text or "")
    filters = _dict(_dict(manifest).get("prompt_filters"))

    # These protocol blocks are never useful as natural-language history. Apply the
    # safe filters even when an old safe-copy predates the emulation manifest.
    if filters.get("status_placeholder", True):
        value = _STATUS_PLACEHOLDER_RE.sub("", value)
    if filters.get("update_variable", True):
        value = _UPDATE_VARIABLE_RE.sub("", value)
        value = _UNCLOSED_UPDATE_RE.sub("", value)
    if filters.get("analysis", True):
        value = _ANALYSIS_RE.sub("", value)

    return re.sub(r"\n{3,}", "\n\n", value).strip()
