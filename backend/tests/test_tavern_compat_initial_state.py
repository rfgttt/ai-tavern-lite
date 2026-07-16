from app.services.tavern_compat.initial_state import extract_card_variables, merge_card_variables


def test_extracts_tavern_helper_stat_data_first():
    normalized = {
        "extensions": {
            "tavern_helper": {
                "variables": {
                    "stat_data": {
                        "世界信息": {"当前地点": "图书馆"},
                        "角色": {"好感度": 12},
                    }
                }
            }
        },
        "character_book": {
            "entries": [
                {"comment": "[initvar]", "enabled": False, "content": "角色:\n  好感度: 99"}
            ]
        },
    }

    result = extract_card_variables(normalized)

    assert result.source == "tavern_helper.variables.stat_data"
    assert result.variables["世界信息"]["当前地点"] == "图书馆"
    assert result.variables["角色"]["好感度"] == 12


def test_extracts_disabled_initvar_yaml_subset():
    normalized = {
        "character_book": {
            "entries": [
                {
                    "comment": "[initvar]",
                    "enabled": False,
                    "content": """
世界信息:
  当前时间: 重光十七年4月7日-9:30
  当前地点: 私立月见崎学院-二年A班教室
  已发现: true
角色:
  好感度: 20
  情绪强度: 50
  特殊物品:
    红色水晶:
      描述: 变身器
  伤病记录: {}
""".strip(),
                },
                {
                    "comment": "关闭的普通条目",
                    "enabled": False,
                    "content": "不应被当作变量",
                },
            ]
        }
    }

    result = extract_card_variables(normalized)

    assert result.source == "worldbook:[initvar]"
    assert result.variables["世界信息"]["已发现"] is True
    assert result.variables["角色"]["好感度"] == 20
    assert result.variables["角色"]["特殊物品"]["红色水晶"]["描述"] == "变身器"
    assert result.variables["角色"]["伤病记录"] == {}
    assert result.warnings == []


def test_merge_card_variables_keeps_platform_roots_and_uses_custom_namespace():
    base = {
        "scene": {},
        "character": {"name": "示例"},
        "relationship": {},
        "custom": {"已有": {"值": 1}},
    }

    merged = merge_card_variables(base, {"世界信息": {"当前地点": "车站"}, "角色": {"好感度": 10}})

    assert merged["character"]["name"] == "示例"
    assert merged["custom"]["已有"]["值"] == 1
    assert merged["custom"]["世界信息"]["当前地点"] == "车站"
    assert merged["custom"]["角色"]["好感度"] == 10


def test_card_variables_project_common_scene_relationship_and_character_fields():
    from app.services.tavern_compat.initial_state import project_card_variables

    state = {
        'scene': {}, 'relationship': {}, 'character': {'name': '角色甲'}, 'custom': {
            '世界信息': {
                '当前时间': '重光十七年4月7日-9:30',
                '当前地点': '学院-二年A班',
                '主角与角色甲的关系': '陌生人',
            },
            '角色甲': {
                '当前状态': 'JK',
                '好感度': 20,
                '情绪强度': 50,
            },
        }
    }

    projected = project_card_variables(state)

    assert projected['scene']['time'] == '重光十七年4月7日-9:30'
    assert projected['scene']['location'] == '学院-二年A班'
    assert projected['relationship']['stage'] == '陌生人'
    assert projected['relationship']['affection'] == 20
    assert projected['character']['state'] == 'JK'
    assert projected['character']['emotion_intensity'] == 50
