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


def test_extracts_disabled_initvar_json_and_projects_mvu_tuples():
    from app.services.tavern_compat.initial_state import project_card_variables

    normalized = {
        "character_book": {
            "entries": [
                {
                    "comment": "[InitVar]",
                    "enabled": False,
                    "content": '''{
                      "$meta": {"strictSet": true},
                      "世界信息": {
                        "日期": ["2024年11月9日", "当前日期"],
                        "时间": ["15:30", "当前时间，格式为 hh:mm"],
                        "地点": ["老旧住宅区的家中", "当前场景地点"]
                      },
                      "穗秋生": {
                        "好感度": [5, "[0-100]爱意程度"],
                        "害怕值": [95, "[0-100]恐惧程度"],
                        "依赖值": [100, "[0-100]依赖程度"],
                        "身上的伤": [["$__META_EXTENSIBLE__$", "额头淤青"], "身体伤势列表"],
                        "重要记忆": [["$__META_EXTENSIBLE__$"], "发生重要事件时记录"]
                      }
                    }''',
                }
            ]
        }
    }

    result = extract_card_variables(normalized)
    projected = project_card_variables({
        "scene": {},
        "relationship": {},
        "character": {"name": "穗秋生"},
        "custom": result.variables,
    })

    assert result.source == "worldbook:[initvar]"
    assert result.warnings == []
    assert result.variables["穗秋生"]["好感度"][0] == 5
    assert projected["scene"] == {
        "location": "老旧住宅区的家中",
        "time": "15:30",
        "date": "2024年11月9日",
    }
    assert projected["relationship"]["affection"] == 5
    assert projected["relationship"]["fear"] == 95
    assert projected["relationship"]["dependence"] == 100
    assert result.variables["穗秋生"]["身上的伤"][0][0] == "$__META_EXTENSIBLE__$"
    assert projected["character"]["injuries"] == ["额头淤青"]
    assert projected["character"]["important_memories"] == []


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
