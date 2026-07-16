from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from ...db.models import Message, Character, Memory
from ..character_parser.parser import replace_template_vars
from ..lorebook.service import LorebookService, LorebookEntry
from ..memory.service import MemoryService
from ...core.logging import logger
from ..runtime.prompt import build_runtime_prompt
from ..tavern_compat.macros import MacroContext, resolve_safe_macros
from ..tavern_compat.lore import is_character_core_lore, is_runtime_protocol_lore
from .planner import build_section_budgets, truncate_text, select_items_with_budget


@dataclass
class PromptSection:
    name: str
    content: str
    estimated_tokens: int
    source: str = ""


@dataclass
class BuiltPrompt:
    messages: List[Dict[str, str]]
    sections: List[PromptSection]
    total_estimated_tokens: int
    context_budget: int
    selected_lorebook_ids: List[Any]


def estimate_tokens(text: str) -> int:
    """Rough token estimation: ~1.7 chars per token for Chinese, ~4 for English."""
    if not text:
        return 0
    # Simple estimation: average 3 chars per token for mixed text
    return max(1, len(text) // 3)


def _select_lore_text(
    entries: List[LorebookEntry],
    max_tokens: int,
    resolved: Dict[int, str],
    heading: str,
) -> Tuple[List[LorebookEntry], str]:
    """Select whole entries and clip one important oversized tail instead of dropping it."""
    if not entries or max_tokens <= 0:
        return [], ""
    heading_cost = estimate_tokens(heading)
    remaining = max(0, max_tokens - heading_cost)
    selected: List[LorebookEntry] = []
    rendered: List[str] = []
    for entry in entries:
        label = entry.comment or f"条目 #{entry.id}"
        block = f"【{label}】\n{resolved.get(id(entry), '').strip()}".strip()
        cost = estimate_tokens(block)
        if cost <= remaining:
            selected.append(entry)
            rendered.append(block)
            remaining -= cost
            continue
        # Preserve a meaningful prefix of the next high-priority entry. This is
        # especially important for large world/character definitions in Tavern cards.
        if remaining >= 48:
            clipped = truncate_text(block, remaining, estimate_tokens)
            if clipped:
                selected.append(entry)
                rendered.append(clipped)
            break
    if not rendered:
        return [], ""
    return selected, truncate_text(heading + "\n" + "\n\n".join(rendered), max_tokens, estimate_tokens)


class PromptBuilder:
    def __init__(
        self,
        character: Character,
        username: str = "用户",
        context_window: int = 8192,
        max_new_tokens: int = 1024
    ):
        self.character = character
        self.username = username
        self.char_name = character.name
        self.context_window = context_window
        self.max_new_tokens = max_new_tokens
        self.context_budget = max(0, context_window - max_new_tokens)

    def build(
        self,
        messages: List[Message],
        lorebook_entries: List[LorebookEntry],
        memories: List[Memory],
        user_message: str = "",
        runtime_profile: Dict[str, Any] | None = None,
        runtime_state: Dict[str, Any] | None = None,
        persona: Dict[str, Any] | None = None,
        group_characters: List[Character] | None = None,
        lorebook_catalog: List[LorebookEntry] | None = None,
    ) -> BuiltPrompt:
        """Build a budgeted prompt that never lets optional lore erase recent chat."""
        budgets = build_section_budgets(self.context_budget)
        sections: List[PromptSection] = []

        group_characters = group_characters or []
        group_mode = len(group_characters) > 1
        catalog = lorebook_catalog or lorebook_entries
        lorebook_by_name: Dict[str, str] = {}
        for entry in catalog:
            title = str(entry.comment or "").strip()
            if title:
                lorebook_by_name.setdefault(title, str(entry.content or ""))
            for key in entry.keys or []:
                key_text = str(key).strip()
                if key_text:
                    lorebook_by_name.setdefault(key_text, str(entry.content or ""))
        macro_context = MacroContext(
            char_name=self.char_name,
            user_name=self.username,
            runtime_state=runtime_state or {},
            lorebook_by_name=lorebook_by_name,
        )
        mem_text = MemoryService.build_memory_text(memories) if memories else ""
        mem_text = truncate_text(mem_text, budgets["memory"], estimate_tokens)
        post_hist_text = truncate_text(
            self._get_post_history_instructions(macro_context), budgets["post_history"], estimate_tokens
        )

        platform_rules_text = self._build_platform_rules()
        if group_mode:
            platform_rules_text += "\n8. 当前为多人剧情。按场景需要切换说话人，并在台词前明确标注角色名。"
        platform_rules = truncate_text(platform_rules_text, budgets["platform"], estimate_tokens)

        char_parts = [self._build_character_info(macro_context)]
        if persona:
            char_parts.append(
                "【玩家 Persona】\n"
                f"名称：{persona.get('name', self.username)}\n"
                f"代称：{persona.get('pronouns', '')}\n"
                f"设定：{persona.get('description', '')}"
            )
        if group_characters:
            cast_lines = ["【多人剧情出演表】"]
            for actor in group_characters:
                cast_lines.append(
                    f"- {actor.name}：{getattr(actor, 'description', '')}；性格：{getattr(actor, 'personality', '')}"
                )
            cast_lines.append('请只让当前场景中合理出现的角色发言，并用“角色名：『台词』”或“角色名：\"台词\"”标注说话人。')
            char_parts.append("\n".join(cast_lines))
        ordered_lore = sorted(
            lorebook_entries,
            key=lambda item: (not bool(item.constant), int(item.insertion_order or 0), str(item.comment or "")),
        )
        resolved_lore = {
            id(entry): resolve_safe_macros(str(entry.content or ""), macro_context).strip()
            for entry in ordered_lore
        }
        character_lore = [entry for entry in ordered_lore if is_character_core_lore(entry)]
        runtime_lore = [
            entry for entry in ordered_lore
            if not is_character_core_lore(entry) and is_runtime_protocol_lore(entry)
        ]
        general_lore = [
            entry for entry in ordered_lore
            if not is_character_core_lore(entry) and not is_runtime_protocol_lore(entry)
        ]

        base_char_text = "\n\n".join(char_parts)
        remaining_character_budget = max(0, budgets["character"] - estimate_tokens(base_char_text))
        selected_character_lore, core_text = _select_lore_text(
            character_lore, remaining_character_budget, resolved_lore, "【角色卡核心设定】"
        )
        if core_text:
            char_parts.append(core_text)
        char_info = truncate_text("\n\n".join(char_parts), budgets["character"], estimate_tokens)

        platform_unused = max(0, budgets["platform"] - estimate_tokens(platform_rules))
        memory_unused = max(0, budgets["memory"] - estimate_tokens(mem_text))
        post_unused = max(0, budgets["post_history"] - estimate_tokens(post_hist_text))
        flexible_spare = platform_unused + memory_unused + post_unused
        # Keep the ordinary World Info cap stable. Unused platform/memory/post-history
        # budget is lent only to card runtime protocols, which otherwise crowd out
        # character and world definitions on MVU-heavy cards.
        runtime_budget = budgets["runtime"] + flexible_spare
        lore_budget = budgets["lorebook"]

        runtime_base = build_runtime_prompt(runtime_profile, runtime_state)
        runtime_remaining = max(0, runtime_budget - estimate_tokens(runtime_base))
        selected_runtime_lore, runtime_protocol_text = _select_lore_text(
            runtime_lore, runtime_remaining, resolved_lore, "【角色卡运行协议】"
        )
        runtime_text = truncate_text(
            "\n\n".join(part for part in (runtime_base, runtime_protocol_text) if part),
            runtime_budget,
            estimate_tokens,
        )

        selected_lore, lore_text = _select_lore_text(
            general_lore, lore_budget, resolved_lore, "【世界书设定】"
        )

        user_message_in_history = bool(
            user_message
            and messages
            and messages[-1].role == "user"
            and messages[-1].content == user_message
        )
        pending_user_message = "" if user_message_in_history else user_message
        pending_tokens = estimate_tokens(pending_user_message)

        # Flexible Tavern protocols may borrow unused optional budgets, but never the
        # recent-chat floor. Trim ordinary lore first, then runtime protocol text.
        history_floor = min(
            budgets["history"],
            max(0, self.context_budget - pending_tokens - estimate_tokens(post_hist_text)),
        )
        essential_fixed = sum(estimate_tokens(text) for text in (platform_rules, char_info, mem_text))
        optional_limit = max(
            0,
            self.context_budget
            - pending_tokens
            - estimate_tokens(post_hist_text)
            - history_floor
            - essential_fixed,
        )
        runtime_tokens = estimate_tokens(runtime_text)
        lore_tokens = estimate_tokens(lore_text)
        overflow = max(0, runtime_tokens + lore_tokens - optional_limit)
        if overflow and lore_tokens:
            next_lore_budget = max(0, lore_tokens - overflow)
            lore_text = truncate_text(lore_text, next_lore_budget, estimate_tokens)
            overflow = max(0, overflow - lore_tokens)
        if overflow and runtime_tokens:
            runtime_text = truncate_text(runtime_text, max(0, runtime_tokens - overflow), estimate_tokens)

        fixed_pairs = [
            ("平台规则", platform_rules, "system"),
            ("角色设定", char_info, f"character_card + {len(selected_character_lore)} 条角色核心设定"),
            ("沉浸状态", runtime_text, f"session_runtime + {len(selected_runtime_lore)} 条运行协议"),
            ("世界书", lore_text, f"{len(selected_lore)}/{len(general_lore)} 条纳入预算"),
            ("长期记忆", mem_text, f"{len(memories)} 条候选" if memories else "无相关记忆"),
        ]
        fixed_tokens = sum(estimate_tokens(content) for _, content, _ in fixed_pairs)
        post_tokens = estimate_tokens(post_hist_text)
        available_history = max(0, self.context_budget - fixed_tokens - post_tokens - pending_tokens)
        # Preserve at least the planned share when other sections under-use their quotas.
        available_history = max(min(budgets["history"], self.context_budget), available_history)
        max_possible_history = max(0, self.context_budget - fixed_tokens - post_tokens - pending_tokens)
        available_history = min(available_history, max_possible_history)
        trimmed_messages, hist_tokens = self._trim_history(messages, available_history)

        for name, content, source in fixed_pairs:
            sections.append(PromptSection(name=name, content=content, estimated_tokens=estimate_tokens(content), source=source))
        sections.append(PromptSection(
            name="聊天历史",
            content=f"{len(trimmed_messages)} 条消息",
            estimated_tokens=hist_tokens,
            source=f"保留最近消息，裁剪 {max(0, len(messages) - len(trimmed_messages))} 条",
        ))
        if post_hist_text:
            sections.append(PromptSection(
                name="后历史指令", content=post_hist_text, estimated_tokens=post_tokens, source="character_card"
            ))

        final_messages = self._assemble_messages(
            platform_rules=platform_rules,
            char_info=char_info,
            runtime_text=runtime_text,
            lore_text=lore_text,
            mem_text=mem_text,
            history_messages=trimmed_messages,
            post_hist_text=post_hist_text,
            user_message=pending_user_message,
            macro_context=macro_context,
        )
        total_tokens = sum(section.estimated_tokens for section in sections) + pending_tokens
        return BuiltPrompt(
            messages=final_messages,
            sections=sections,
            total_estimated_tokens=min(total_tokens, self.context_budget),
            context_budget=self.context_budget,
            selected_lorebook_ids=[
                entry.id for entry in [*selected_character_lore, *selected_runtime_lore, *selected_lore]
            ],
        )

    def _build_platform_rules(self) -> str:
        """Build platform-level roleplay rules."""
        return f"""你正在进行角色扮演。你需要扮演 {self.char_name}，严格保持角色设定。

规则：
1. 不要自称AI助手，不要提及你是人工智能或程序。
2. 保持角色的性格、语气、知识背景和行为方式一致。
3. 不要替用户决定行动，只描述角色自己的言行。
4. 不要编造用户没有说过的经历。
5. 可以自然地进行叙事、动作描写和对话。
6. 使用和用户最近消息相同的语言回复。
7. 保持在角色设定的场景内互动。"""

    def _build_character_info(self, macro_context: MacroContext) -> str:
        """Build character core info section."""
        import json
        try:
            norm = json.loads(self.character.normalized_json) if self.character.normalized_json else {}
        except (json.JSONDecodeError, TypeError):
            norm = {}

        parts = []
        parts.append(f"角色名称：{self.char_name}")

        if self.character.description:
            parts.append(f"\n角色描述：\n{self.character.description}")

        if self.character.personality:
            parts.append(f"\n性格：{self.character.personality}")

        if self.character.scenario:
            parts.append(f"\n场景：{self.character.scenario}")

        sys_prompt = norm.get("system_prompt", "")
        if sys_prompt:
            parts.append(f"\n系统提示：{sys_prompt}")

        creator_notes = norm.get("creator_notes", "")
        if creator_notes:
            parts.append(f"\n创作者备注：{creator_notes}")

        mes_example = norm.get("mes_example", "")
        if mes_example:
            parts.append(f"\n对话示例：\n{mes_example}")

        info = "\n".join(parts)
        return resolve_safe_macros(info, macro_context)

    def _get_post_history_instructions(self, macro_context: MacroContext) -> str:
        """Get post_history_instructions from character card."""
        import json
        try:
            norm = json.loads(self.character.normalized_json) if self.character.normalized_json else {}
        except (json.JSONDecodeError, TypeError):
            norm = {}

        text = norm.get("post_history_instructions", "")
        return resolve_safe_macros(text, macro_context) if text else ""

    def _trim_history(
        self,
        messages: List[Message],
        max_tokens: int
    ) -> Tuple[List[Message], int]:
        """Keep the newest contiguous history suffix that fits the budget."""
        if not messages or max_tokens <= 0:
            return [], 0

        kept: List[Message] = []
        total_tokens = 0
        for msg in reversed(messages):
            msg_tokens = estimate_tokens(msg.content)
            if total_tokens + msg_tokens > max_tokens:
                break
            kept.append(msg)
            total_tokens += msg_tokens

        kept.reverse()
        return kept, total_tokens

    def _assemble_messages(
        self,
        platform_rules: str,
        char_info: str,
        runtime_text: str,
        lore_text: str,
        mem_text: str,
        history_messages: List[Message],
        post_hist_text: str,
        user_message: str,
        macro_context: MacroContext,
    ) -> List[Dict[str, str]]:
        """Assemble all parts into OpenAI-compatible messages list."""
        messages = []

        # Build system prompt from all fixed sections
        system_parts = [platform_rules, char_info]
        if runtime_text:
            system_parts.append(runtime_text)
        if lore_text:
            system_parts.append(lore_text)
        if mem_text:
            system_parts.append(mem_text)

        system_content = "\n\n".join(system_parts)
        messages.append({"role": "system", "content": system_content})

        # Add history messages
        for msg in history_messages:
            role = msg.role
            content = resolve_safe_macros(msg.content, macro_context)
            messages.append({"role": role, "content": content})

        # Add post_history_instructions as a final system message before user
        if post_hist_text:
            messages.append({"role": "system", "content": post_hist_text})

        # Add current user message
        if user_message:
            messages.append({"role": "user", "content": resolve_safe_macros(user_message, macro_context)})

        return messages
