import json

import pytest


def dnd_like_normalized():
    return {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "name": "D&D Adventure",
        "description": "A rules-driven fantasy adventure.",
        "scenario": "An ancient dungeon",
        "first_mes": "[Start]",
        "alternate_greetings": [],
        "extensions": {
            "world": "D&D 2024",
            "regex_scripts": [
                {"scriptName": "状态栏", "findRegex": "<StatusPlaceHolderImpl/>", "replaceString": "<div>ignored</div>"},
                {"scriptName": "骰子", "findRegex": "/<dice>/g", "replaceString": "<div>ignored</div>"},
                {"scriptName": "battle", "findRegex": "/<battle>/g", "replaceString": "<script>ignored</script>"},
            ],
            "tavern_helper": {
                "scripts": [
                    {"name": "变量结构", "content": "registerMvuSchema(Schema); 角色列表 生命值 护甲等级"}
                ]
            },
        },
        "character_book": {
            "entries": [
                {"id": 1, "comment": "战斗面板", "keys": [], "content": "Use <battle> during combat", "enabled": True},
                {"id": 2, "comment": "变量格式", "keys": [], "content": "<UpdateVariable><JSONPatch>", "enabled": True},
            ]
        },
    }


def test_analyze_card_recognizes_safe_runtime_capabilities():
    from app.services.runtime.card_profile import analyze_card

    profile = analyze_card(dnd_like_normalized())

    assert profile["mode"] == "adventure"
    assert profile["capabilities"]["mvu_state"] is True
    assert profile["capabilities"]["mvu_json_patch_protocol"] is True
    assert profile["capabilities"]["mvu_command_protocol"] is False
    assert profile["capabilities"]["dice"] is True
    assert profile["capabilities"]["battle"] is True
    assert profile["capabilities"]["worldbook"] is True
    assert profile["script_execution"] == "safe-native-emulation"
    assert profile["native_renderers"] == ["state", "dice", "battle_check", "battle_map"]
    assert profile["regex_script_count"] == 3


def test_general_card_gets_relationship_friendly_defaults(sample_v3_character_json):
    from app.services.character_parser.parser import parse_json_character
    from app.services.runtime.card_profile import analyze_card
    from app.services.runtime.state_engine import build_initial_state

    normalized, _ = parse_json_character(sample_v3_character_json)
    profile = analyze_card(normalized.to_dict())
    state = build_initial_state(profile, normalized.to_dict(), username="测试用户")

    assert profile["mode"] == "relationship"
    assert state["scene"]["location"] == "图书馆场景"
    assert state["relationship"]["affection"] == 0
    assert state["relationship"]["stage"] == "初识"
    assert state["player"]["name"] == "测试用户"


def test_apply_patch_supports_delta_insert_and_clamps():
    from app.services.runtime.state_engine import apply_patch

    state = {
        "relationship": {"affection": 98, "trust": 4},
        "player": {"hp": 10, "max_hp": 12, "conditions": []},
        "custom": {},
    }
    result = apply_patch(
        state,
        [
            {"op": "delta", "path": "/relationship/affection", "value": 9},
            {"op": "increment", "path": "/player/hp", "value": -3},
            {"op": "insert", "path": "/player/conditions/-", "value": "poisoned"},
            {"op": "add", "path": "/custom/clue", "value": "etched rune"},
        ],
    )

    assert result.state["relationship"]["affection"] == 100
    assert result.state["player"]["hp"] == 7
    assert result.state["player"]["conditions"] == ["poisoned"]
    assert result.state["custom"]["clue"] == "etched rune"
    assert result.rejected == []


def test_apply_patch_supports_mvu_collection_ops_and_custom_stat_clamping():
    from app.services.runtime.state_engine import apply_patch

    state = {
        'relationship': {},
        'character': {'name': '穗秋生'},
        'custom': {
            '穗秋生': {
                '好感度': [99, '[0-100]爱意程度'],
                '害怕值': [95, '[0-100]恐惧程度'],
                '身上的伤': [['头皮裂伤', '额头淤青'], '身体伤势列表'],
                '重要记忆': [[], '发生重要事件时记录'],
            },
        },
    }

    result = apply_patch(state, [
        {'op': 'increment', 'path': '/custom/穗秋生/好感度/0', 'value': 5},
        {'op': 'append', 'path': '/custom/穗秋生/重要记忆/0', 'value': '第一次被温柔安慰'},
        {'op': 'remove_at', 'path': '/custom/穗秋生/重要记忆/0', 'index': 0},
        {'op': 'append', 'path': '/custom/穗秋生/重要记忆/0', 'value': '第一次被温柔安慰'},
        {'op': 'remove_value', 'path': '/custom/穗秋生/身上的伤/0', 'value': '头皮裂伤'},
    ])

    assert result.rejected == []
    assert result.state['custom']['穗秋生']['好感度'][0] == 100
    assert result.state['custom']['穗秋生']['重要记忆'][0] == ['第一次被温柔安慰']
    assert result.state['custom']['穗秋生']['身上的伤'][0] == ['额头淤青']
    assert result.state['relationship']['affection'] == 100
    assert result.state['relationship']['fear'] == 95
    assert result.state['character']['important_memories'] == ['第一次被温柔安慰']


def test_apply_patch_rejects_private_and_pollution_paths():
    from app.services.runtime.state_engine import apply_patch

    state = {"custom": {}, "relationship": {"affection": 0}}
    result = apply_patch(
        state,
        [
            {"op": "replace", "path": "/_internal/key", "value": 1},
            {"op": "add", "path": "/custom/__proto__/polluted", "value": True},
            {"op": "replace", "path": "/missing/path", "value": 1},
        ],
    )

    assert len(result.rejected) == 3
    assert result.state == state


def test_character_parser_embeds_runtime_profile(sample_v3_character_json):
    from app.services.character_parser.parser import parse_json_character

    normalized, _ = parse_json_character(sample_v3_character_json)
    payload = normalized.to_dict()

    assert "ai_tavern_runtime" in payload
    assert payload["ai_tavern_runtime"]["script_execution"] == "disabled"


def test_disabled_worldbook_entries_do_not_influence_runtime_profile():
    from app.services.runtime.card_profile import analyze_card

    profile = analyze_card({
        "name": "普通角色",
        "description": "安静的日常角色卡",
        "extensions": {},
        "character_book": {
            "entries": [
                {
                    "comment": "停用扩展",
                    "content": "D&D <battle> <dice> UpdateVariable JSONPatch",
                    "enabled": False,
                }
            ]
        },
    })

    assert profile["mode"] == "relationship"
    assert profile["capabilities"]["battle"] is False
    assert profile["capabilities"]["dice"] is False
    assert profile["lorebook_entry_count"] == 0


def test_plain_card_does_not_claim_native_relationship_state():
    from app.services.runtime.card_profile import analyze_card

    profile = analyze_card({
        "name": "普通角色",
        "description": "一位住在海边的画家",
        "scenario": "海边画室",
        "extensions": {},
    })

    assert profile["capabilities"]["relationship_state"] is False
    assert profile["capabilities"]["scene_state"] is True


def test_card_with_relationship_protocol_claims_relationship_state():
    from app.services.runtime.card_profile import analyze_card

    profile = analyze_card({
        "name": "关系卡",
        "description": "通过变量记录亲密度",
        "extensions": {
            "tavern_helper": {
                "scripts": [{"name": "关系变量", "content": "好感度 信任度 relationship UpdateVariable"}]
            }
        },
    })

    assert profile["capabilities"]["relationship_state"] is True
