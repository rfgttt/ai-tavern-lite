from __future__ import annotations

from typing import Any

from ...db.models import Memory
from ..lorebook.service import LorebookEntry, LorebookService
from ..memory.service import MemoryService
from ..tavern_compat.lore import is_character_core_lore, is_runtime_protocol_lore
from .builder import BuiltPrompt, estimate_tokens

_TRUNCATION_MARKERS = ("…（该部分因上下文预算截断）", "…")
_SECTION_KEYS = {
    "平台规则": "platform",
    "角色设定": "character",
    "沉浸状态": "runtime",
    "世界书": "lorebook",
    "长期记忆": "memory",
    "聊天历史": "history",
    "后历史指令": "post_history",
}


def _is_truncated(text: str) -> bool:
    stripped = (text or "").rstrip()
    return any(stripped.endswith(marker) for marker in _TRUNCATION_MARKERS)


def _visible_prefix_length(final_text: str, original_text: str) -> int:
    if final_text == original_text:
        return len(original_text)
    stripped = final_text.rstrip()
    for marker in _TRUNCATION_MARKERS:
        if stripped.endswith(marker):
            prefix = stripped[: -len(marker)].rstrip()
            return min(len(prefix), len(original_text))
    return min(len(final_text), len(original_text))


def _memory_scope(memory: Memory) -> str:
    return MemoryService.scope_name(memory.character_id, memory.session_id)


def _memory_line(memory: Memory) -> str:
    category = MemoryService.normalize_category(memory.category)
    return f"- [{category}] {memory.content.strip()}"


def _memory_inclusions(
    selected_memories: list[Memory],
    final_memory_text: str,
) -> dict[str, tuple[bool, bool, str]]:
    """Map selected rows to their exact rendered positions, including duplicate text."""
    if not selected_memories:
        return {}
    heading = "【长期记忆】"
    lines = [_memory_line(memory) for memory in selected_memories]
    original_text = "\n".join([heading, *lines])
    prefix_len = _visible_prefix_length(final_memory_text, original_text)
    cursor = len(heading) + 1
    result: dict[str, tuple[bool, bool, str]] = {}
    for memory, line in zip(selected_memories, lines):
        start = cursor
        end = start + len(line)
        if end <= prefix_len:
            result[memory.id] = (True, False, "included")
        elif start < prefix_len:
            result[memory.id] = (True, True, "memory_budget_partial")
        else:
            result[memory.id] = (False, False, "memory_budget")
        cursor = end + 1
    return result


def _entry_kind(entry: LorebookEntry) -> str:
    if is_character_core_lore(entry):
        return "character_core"
    if is_runtime_protocol_lore(entry):
        return "runtime_protocol"
    return "world"


def _matched_keys(entry: LorebookEntry, recent_text: str) -> tuple[list[str], list[str]]:
    scan_text = recent_text[-2000:] if len(recent_text) > 2000 else recent_text
    scan_lower = scan_text.lower()
    primary = [
        str(key)
        for key in entry.keys
        if key and LorebookService._key_matches(str(key), entry.use_regex, scan_text, scan_lower)
    ]
    secondary = [
        str(key)
        for key in entry.secondary_keys
        if key and LorebookService._key_matches(str(key), entry.use_regex, scan_text, scan_lower)
    ]
    return primary, secondary


def _lore_reason(
    entry: LorebookEntry,
    *,
    triggered: bool,
    included: bool,
    primary_matches: list[str],
    secondary_matches: list[str],
) -> str:
    if not entry.enabled:
        return "disabled"
    if not str(entry.content or "").strip():
        return "empty_content"
    if included:
        return "included"
    if triggered:
        return "context_budget"
    if entry.constant:
        return "probability_or_duplicate_filter"
    if not primary_matches:
        return "no_primary_match"
    if entry.selective and entry.secondary_keys and not secondary_matches:
        return "no_secondary_match"
    return "probability_or_duplicate_filter"


def build_prompt_inspection(
    *,
    built_prompt: BuiltPrompt,
    context_window: int,
    max_new_tokens: int,
    memory_catalog: list[Memory],
    selected_memories: list[Memory],
    lorebook_catalog: list[LorebookEntry],
    triggered_lorebook: list[LorebookEntry],
    recent_text: str,
) -> dict[str, Any]:
    """Build a read-only explanation from an already-built prompt.

    This function must never influence prompt selection or rendering. It observes the
    completed ``BuiltPrompt`` and the same candidates used by preview preparation.
    """
    sections_by_name = {section.name: section for section in built_prompt.sections}
    section_reports: list[dict[str, Any]] = []
    for section in built_prompt.sections:
        key = _SECTION_KEYS.get(section.name, section.name)
        truncated = bool(
            built_prompt.section_truncated.get(key, _is_truncated(section.content))
        )
        included = bool(section.content)
        if key == "history":
            included = built_prompt.history_included_count > 0
        section_reports.append(
            {
                "key": key,
                "name": section.name,
                "budget_tokens": int(built_prompt.section_budgets.get(key, 0)),
                "estimated_tokens": section.estimated_tokens,
                "included": included,
                "truncated": truncated,
                "reason": "context_budget" if truncated else ("included" if included else "empty"),
                "source": section.source,
            }
        )

    section_reports.append(
        {
            "key": "user_message",
            "name": "当前用户消息",
            "budget_tokens": 0,
            "estimated_tokens": built_prompt.pending_user_tokens,
            "included": built_prompt.pending_user_tokens > 0,
            "truncated": False,
            "reason": "included" if built_prompt.pending_user_tokens > 0 else "already_in_history_or_empty",
            "source": "request.message",
        }
    )

    memory_text = sections_by_name.get("长期记忆").content if sections_by_name.get("长期记忆") else ""
    memory_reports: list[dict[str, Any]] = []
    memory_inclusions = _memory_inclusions(selected_memories, memory_text)
    selected_memory_ids = {item.id for item in selected_memories}
    ordered_memory_catalog = [
        *selected_memories,
        *(memory for memory in memory_catalog if memory.id not in selected_memory_ids),
    ]
    for memory in ordered_memory_catalog:
        if not memory.enabled:
            included, truncated, reason = False, False, "disabled"
        elif memory.id not in selected_memory_ids:
            included, truncated, reason = False, False, "entry_limit"
        else:
            included, truncated, reason = memory_inclusions.get(
                memory.id, (False, False, "not_rendered")
            )
        memory_reports.append(
            {
                "id": memory.id,
                "category": MemoryService.normalize_category(memory.category),
                "scope": _memory_scope(memory),
                "content": memory.content,
                "importance": float(memory.importance or 0),
                "enabled": bool(memory.enabled),
                "selected": memory.id in selected_memory_ids,
                "included": included,
                "truncated": truncated,
                "estimated_tokens": estimate_tokens(_memory_line(memory)),
                "reason": reason,
            }
        )

    selected_lore_object_ids = set(built_prompt.selected_lorebook_object_ids)
    triggered_object_ids = {id(entry) for entry in triggered_lorebook}
    lore_reports: list[dict[str, Any]] = []
    for entry in lorebook_catalog:
        kind = _entry_kind(entry)
        primary_matches, secondary_matches = _matched_keys(entry, recent_text)
        triggered = id(entry) in triggered_object_ids
        selected = triggered and id(entry) in selected_lore_object_ids
        original_content = str(entry.content or "")
        resolved_content = built_prompt.lorebook_resolved_content.get(
            id(entry), original_content
        )
        injected_content = built_prompt.lorebook_injected_content.get(id(entry), "")
        included = bool(injected_content)
        label = str(entry.comment or f"条目 #{entry.id}")
        expected_block = f"【{label}】\n{resolved_content.strip()}".strip()
        truncated = bool(included and injected_content != expected_block)
        reason = _lore_reason(
            entry,
            triggered=triggered,
            included=included,
            primary_matches=primary_matches,
            secondary_matches=secondary_matches,
        )
        if truncated:
            reason = "included_partial"
        lore_reports.append(
            {
                "id": str(entry.id),
                "title": str(entry.comment or f"条目 #{entry.id}"),
                "kind": kind,
                "enabled": bool(entry.enabled),
                "constant": bool(entry.constant),
                "probability": int(entry.probability or 0),
                "keys": [str(key) for key in entry.keys if key],
                "matched_keys": primary_matches,
                "secondary_matched_keys": secondary_matches,
                "triggered": triggered,
                "selected": selected,
                "included": included,
                "truncated": truncated,
                "content": original_content,
                "resolved_content": resolved_content,
                "injected_content": injected_content,
                "content_characters": len(original_content),
                "resolved_characters": len(resolved_content),
                "injected_characters": len(injected_content),
                "estimated_tokens": estimate_tokens(resolved_content),
                "reason": reason,
            }
        )

    history_section = sections_by_name.get("聊天历史")
    included_count = built_prompt.history_included_count
    total_count = built_prompt.history_total_count
    history_report = {
        "total_messages": total_count,
        "included_messages": included_count,
        "trimmed_messages": max(0, total_count - included_count),
        "earliest_included_sequence": built_prompt.history_earliest_sequence,
        "budget_tokens": int(built_prompt.section_budgets.get("history", 0)),
        "estimated_tokens": history_section.estimated_tokens if history_section else 0,
    }

    estimated = int(built_prompt.total_estimated_tokens)
    budget = int(built_prompt.context_budget)
    return {
        "summary": {
            "context_window": int(context_window),
            "reserved_output_tokens": int(max_new_tokens),
            "input_budget": budget,
            "estimated_input_tokens": estimated,
            "remaining_tokens": max(0, budget - estimated),
            "usage_percent": round((estimated / budget * 100), 1) if budget else 0.0,
        },
        "sections": section_reports,
        "memories": memory_reports,
        "lorebook": lore_reports,
        "history": history_report,
    }
