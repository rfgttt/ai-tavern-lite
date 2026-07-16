from __future__ import annotations

import re
from typing import Any

_CHARACTER_CORE_HINTS = (
    "角色信息", "角色设定", "角色档案", "人物信息", "人物设定", "人物档案",
    "character profile", "character info", "character definition", "character sheet",
)


def is_character_core_lore(entry: Any) -> bool:
    """Identify lore entries that define the acting character rather than world facts.

    This is deliberately based on common ecosystem labels/markup, never a card name.
    """
    comment = str(getattr(entry, "comment", "") or "").strip().lower()
    content = str(getattr(entry, "content", "") or "").lstrip().lower()
    if any(hint in comment for hint in _CHARACTER_CORE_HINTS):
        return True
    return bool(re.match(r"<(?:character|persona|character_profile)\b", content, flags=re.IGNORECASE))

_RUNTIME_PROTOCOL_HINTS = (
    "mvu", "变量更新", "变量列表", "变量输出", "variable protocol", "variable update",
    "output format", "status variables", "stat_data", "jsonpatch", "updatevariable",
)


def is_runtime_protocol_lore(entry: Any) -> bool:
    comment = str(getattr(entry, "comment", "") or "").strip().lower()
    content = str(getattr(entry, "content", "") or "").lower()
    if any(hint in comment for hint in _RUNTIME_PROTOCOL_HINTS):
        return True
    return any(token in content for token in (
        "<updatevariable", "<update_variable", "<jsonpatch", "format_message_variable::stat_data",
        "<status_current_variables>",
    ))
