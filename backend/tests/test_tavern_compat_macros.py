from app.services.tavern_compat.macros import MacroContext, resolve_safe_macros


def test_resolves_identity_and_read_only_variable_macros():
    context = MacroContext(
        char_name='雾叶泠',
        user_name='林舟',
        runtime_state={
            'scene': {'location': '教室'},
            'custom': {'雾叶泠': {'好感度': 20}, '世界信息': {'当前地点': '二年A班'}},
        },
    )
    text = '<user>与{{char}}：{{getvar::stat_data.雾叶泠.好感度}} / {{getvar::scene.location}}'

    result = resolve_safe_macros(text, context)

    assert result == '林舟与雾叶泠：20 / 教室'


def test_formats_stat_data_as_readable_json():
    context = MacroContext(char_name='A', user_name='B', runtime_state={'custom': {'角色': {'数值': 7}}})
    result = resolve_safe_macros('{{format_message_variable::stat_data}}', context)
    assert '"角色"' in result
    assert '"数值": 7' in result


def test_safely_resolves_common_getwi_conditional_without_javascript_execution():
    context = MacroContext(
        char_name='A',
        user_name='B',
        runtime_state={'custom': {'角色': {'好感度': 45}}},
        lorebook_by_name={
            '阶段1': '保持疏远。',
            '阶段2': '已经熟悉，会自然关心用户。',
        },
    )
    text = '''规则：
<%_ const aff = getvar("stat_data.角色.好感度"); _%>
<%_ if (aff <= 40) { _%><%- await getwi(null, '阶段1') %><%_
} else if (aff > 40) { _%><%- await getwi(null, '阶段2') %><%_
} _%>
结束。'''

    result = resolve_safe_macros(text, context)

    assert '已经熟悉' in result
    assert '保持疏远' not in result
    assert '<%' not in result


def test_unknown_or_unsafe_ejs_is_removed_not_executed():
    context = MacroContext(char_name='A', user_name='B', runtime_state={})
    result = resolve_safe_macros('前文<% fetch("https://bad.example") %>后文', context)
    assert result == '前文后文'


def test_prompt_builder_resolves_runtime_macros_and_disabled_getwi_catalog():
    import json
    from types import SimpleNamespace

    from app.services.lorebook.service import LorebookEntry
    from app.services.prompt_builder.builder import PromptBuilder

    normalized = {
        'system_prompt': '',
        'creator_notes': '',
        'mes_example': '',
        'post_history_instructions': '',
    }
    character = SimpleNamespace(
        name='角色甲', description='', personality='', scenario='',
        normalized_json=json.dumps(normalized, ensure_ascii=False),
    )
    active = LorebookEntry({
        'id': 1, 'comment': '变量规则', 'constant': True, 'enabled': True,
        'content': '''当前变量：{{format_message_variable::stat_data}}
<%_ const score = getvar("stat_data.角色甲.好感度"); _%>
<%_ if (score < 40) { _%><%- await getwi(null, '阶段低') %><%_ } else { _%><%- await getwi(null, '阶段高') %><%_ } _%>''',
    })
    low = LorebookEntry({'id': 2, 'comment': '阶段低', 'enabled': False, 'content': '保持距离。'})
    high = LorebookEntry({'id': 3, 'comment': '阶段高', 'enabled': False, 'content': '态度亲近。'})

    built = PromptBuilder(character).build(
        messages=[], lorebook_entries=[active], lorebook_catalog=[active, low, high], memories=[],
        runtime_state={'custom': {'角色甲': {'好感度': 55}}}, runtime_profile={},
    )
    system = built.messages[0]['content']
    assert '"好感度": 55' in system
    assert '态度亲近' in system
    assert '保持距离' not in system
    assert '<%' not in system
