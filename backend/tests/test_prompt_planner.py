from types import SimpleNamespace


def _message(role: str, content: str, sequence: int):
    return SimpleNamespace(role=role, content=content, sequence=sequence)


def test_section_budgets_reserve_recent_chat():
    from app.services.prompt_builder.planner import build_section_budgets

    budgets = build_section_budgets(7000)

    assert budgets["history"] >= 2100
    assert budgets["lorebook"] <= 1400
    assert sum(budgets.values()) <= 7000


def test_prompt_builder_keeps_recent_turns_when_card_and_lore_are_huge(db_with_character):
    from app.services.lorebook.service import LorebookEntry
    from app.services.prompt_builder.builder import PromptBuilder

    _, character = db_with_character
    character.description = "角色核心" * 5000
    messages = []
    for index in range(12):
        messages.append(_message("user", f"第{index}轮用户消息 " + "内容" * 80, index * 2))
        messages.append(_message("assistant", f"第{index}轮角色回复 " + "回应" * 80, index * 2 + 1))
    lore = [
        LorebookEntry({
            "id": index,
            "comment": f"条目{index}",
            "content": "世界书内容" * 500,
            "constant": True,
            "enabled": True,
            "insertion_order": index,
        })
        for index in range(12)
    ]

    built = PromptBuilder(character, context_window=8192, max_new_tokens=1024).build(
        messages=messages,
        lorebook_entries=lore,
        memories=[],
        runtime_profile={},
        runtime_state={},
    )

    history_messages = [item for item in built.messages if item["role"] in {"user", "assistant"}]
    assert len(history_messages) >= 6
    assert "第11轮角色回复" in history_messages[-1]["content"]
    lore_section = next(item for item in built.sections if item.name == "世界书")
    assert lore_section.estimated_tokens <= int(built.context_budget * 0.20) + 10
    assert built.total_estimated_tokens <= built.context_budget


def test_prompt_builder_includes_persona_and_group_cast(db_with_character):
    from app.services.prompt_builder.builder import PromptBuilder

    _, character = db_with_character
    companion = SimpleNamespace(name='莉亚', description='活泼的盗贼', personality='机敏', scenario='')
    built = PromptBuilder(character, context_window=8192, max_new_tokens=1024).build(
        messages=[], lorebook_entries=[], memories=[],
        persona={'name': '北境旅人', 'description': '谨慎而善良', 'pronouns': '他/他'},
        group_characters=[character, companion],
    )
    system = built.messages[0]['content']
    assert '北境旅人' in system
    assert '莉亚' in system
    assert '多人剧情' in system


def test_character_core_lore_uses_character_budget_instead_of_competing_with_runtime_protocol(db_with_character):
    from app.services.lorebook.service import LorebookEntry
    from app.services.prompt_builder.builder import PromptBuilder

    _, character = db_with_character
    character.description = ''
    character.personality = ''
    character.scenario = ''
    runtime_rule = LorebookEntry({
        'id': 90,
        'comment': '[mvu_update] Variable protocol',
        'content': '<UpdateVariable><JSONPatch> ' + ('protocol ' * 360),
        'constant': True,
        'enabled': True,
        'insertion_order': 1,
    })
    character_core = LorebookEntry({
        'id': 91,
        'comment': 'Character Profile',
        'content': '<character>CORE-MARKER Avery is reserved, observant, and never speaks for the user.</character> ' + ('profile ' * 140),
        'constant': True,
        'enabled': True,
        'insertion_order': 100,
    })

    built = PromptBuilder(character, context_window=8192, max_new_tokens=1024).build(
        messages=[], lorebook_entries=[runtime_rule, character_core], memories=[],
        runtime_profile={}, runtime_state={}, lorebook_catalog=[runtime_rule, character_core],
    )

    system = built.messages[0]['content']
    assert 'CORE-MARKER' in system
    assert 91 in built.selected_lorebook_ids


def test_truncate_text_includes_ellipsis_inside_token_limit():
    from app.services.prompt_builder.builder import estimate_tokens
    from app.services.prompt_builder.planner import truncate_text

    clipped = truncate_text('很长的文本' * 100, 9, estimate_tokens)

    assert estimate_tokens(clipped) <= 9
    assert clipped
