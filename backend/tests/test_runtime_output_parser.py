import json


def test_native_runtime_block_is_removed_and_parsed():
    from app.services.runtime.output_parser import parse_runtime_output

    text = "火把照亮了石门。\n<tavern_state>" + json.dumps(
        {
            "patch": [{"op": "delta", "path": "/relationship/trust", "value": 2}],
            "events": ["发现石门"],
            "choices": ["检查符文", "原地警戒"],
            "expression": "警觉",
        },
        ensure_ascii=False,
    ) + "</tavern_state>"

    parsed = parse_runtime_output(text)

    assert parsed.narrative == "火把照亮了石门。"
    assert parsed.patch[0]["path"] == "/relationship/trust"
    assert parsed.events == ["发现石门"]
    assert parsed.choices == ["检查符文", "原地警戒"]
    assert parsed.expression == "警觉"


def test_mvu_update_variable_json_patch_is_converted():
    from app.services.runtime.output_parser import parse_runtime_output

    text = "你拾起了钥匙。\n<UpdateVariable><Analysis>ok</Analysis><JSONPatch>" \
        '[{"op":"delta","path":"/角色列表/艾尔玛/生命值/当前","value":-2}]' \
        "</JSONPatch></UpdateVariable>"

    parsed = parse_runtime_output(text)

    assert parsed.narrative == "你拾起了钥匙。"
    assert parsed.patch == [
        {"op": "delta", "path": "/custom/角色列表/艾尔玛/生命值/当前", "value": -2}
    ]


def test_dice_and_battlecheck_blocks_become_native_metadata():
    from app.services.runtime.output_parser import parse_runtime_output

    text = "弓弦发出短促震响。\n<dice>\n发动技能: 察觉\n目标: 玩家\n情境: 搜索暗门\n检定细节: d20(17)+3=20 vs DC15\n判定结果: 成功（Success）\n结果描述: 发现缝隙\n</dice>\n" \
        "<battlecheck>\n发动者: 莱拉\n目标: 哥布林\n行动: 长弓射击\n检定类型: 远程攻击\n检定细节: d20(15)+5=20 vs AC13\n判定结果: 命中（Hit）\n战果描述: 箭矢命中肩部\n</battlecheck>"

    parsed = parse_runtime_output(text)

    assert parsed.narrative == "弓弦发出短促震响。"
    assert parsed.dice[0]["skill"] == "察觉"
    assert parsed.dice[0]["result"] == "成功（Success）"
    assert parsed.battle_checks[0]["actor"] == "莱拉"
    assert parsed.battle_checks[0]["outcome"] == "命中（Hit）"


def test_battle_block_parses_units_without_executing_html():
    from app.services.runtime.output_parser import parse_runtime_output

    text = "战斗爆发。\n<battle>\n莱拉|init 18|hp 24/28|pos 0,5|att 0|next|status prone\n哥布林|init 12|hp 7/7|pos 15,5|att 2\n</battle>"
    parsed = parse_runtime_output(text)

    assert parsed.narrative == "战斗爆发。"
    assert parsed.battle["active"] is True
    assert parsed.battle["units"][0]["id"] == "莱拉"
    assert parsed.battle["units"][0]["next"] is True
    assert parsed.battle["units"][1]["attitude"] == 2


def test_malformed_runtime_block_does_not_destroy_narrative():
    from app.services.runtime.output_parser import parse_runtime_output

    parsed = parse_runtime_output("正常正文<tavern_state>{broken}</tavern_state>")

    assert parsed.narrative == "正常正文"
    assert parsed.patch == []
    assert parsed.errors


def test_runtime_prompt_contains_state_and_machine_protocol():
    from app.services.runtime.prompt import build_runtime_prompt

    text = build_runtime_prompt(
        {"mode": "adventure", "capabilities": {"dice": True, "battle": True}},
        {"scene": {"location": "古堡"}, "player": {"hp": 8, "max_hp": 10}},
    )

    assert "古堡" in text
    assert "<tavern_state>" in text
    assert '"patch"' in text
    assert "不要输出 HTML" in text


async def _collect_mock_response():
    from app.services.llm.provider import MockLLMProvider

    provider = MockLLMProvider(character_name="林夕")
    return "".join([chunk async for chunk in provider.chat_completion([{"role": "user", "content": "看看酒馆里发生了什么"}])])


def test_mock_provider_demonstrates_runtime_state():
    import asyncio

    from app.services.runtime.output_parser import parse_runtime_output

    parsed = parse_runtime_output(asyncio.run(_collect_mock_response()))

    assert parsed.events
    assert parsed.choices
    assert any(item.get("path") == "/relationship/trust" for item in parsed.patch)


def test_generic_variables_block_is_stored_under_custom_namespace():
    from app.services.runtime.output_parser import parse_runtime_output

    parsed = parse_runtime_output(
        '她放下手中的杯子。\n<variables>{"好感阶段":"熟悉","声望":{"学院":12}}</variables>'
    )

    assert parsed.narrative == '她放下手中的杯子。'
    assert parsed.patch == [
        {"op": "add", "path": "/custom/好感阶段", "value": "熟悉"},
        {"op": "add", "path": "/custom/声望", "value": {"学院": 12}},
    ]


def test_tavern_state_fenced_block_is_hidden_and_parsed():
    from app.services.runtime.output_parser import parse_runtime_output

    parsed = parse_runtime_output(
        '门后的风突然停了。\n```tavern-state\n'
        '{"events":["风声停止"],"patch":[{"op":"add","path":"/custom/危险等级","value":2}]}\n'
        '```'
    )

    assert parsed.narrative == '门后的风突然停了。'
    assert parsed.events == ['风声停止']
    assert parsed.patch[0]["path"] == "/custom/危险等级"


def test_generic_variable_aliases_map_to_card_driven_namespaces():
    from app.services.runtime.output_parser import parse_runtime_output

    parsed = parse_runtime_output(
        '<variables>{"场景":{"地点":"钟楼","天气":"暴雨"},'
        '"关系":{"信任":12,"态度":"谨慎"},'
        '"任务":[{"名称":"寻找钥匙","状态":"进行中"}],'
        '"线索":["门框上的符号"],'
        '"model":"deepseek-chat"}</variables>'
    )

    assert parsed.patch == [
        {"op": "add", "path": "/scene", "value": {"地点": "钟楼", "天气": "暴雨"}},
        {"op": "add", "path": "/relationship", "value": {"信任": 12, "态度": "谨慎"}},
        {"op": "add", "path": "/quests", "value": [{"名称": "寻找钥匙", "状态": "进行中"}]},
        {"op": "add", "path": "/custom/线索", "value": ["门框上的符号"]},
        {"op": "add", "path": "/custom/model", "value": "deepseek-chat"},
    ]


def test_native_patch_normalizes_custom_relationship_alias():
    from app.services.runtime.output_parser import parse_runtime_output

    parsed = parse_runtime_output(
        '<tavern_state>{"patch":['
        '{"op":"add","path":"/custom/relation/信任","value":18},'
        '{"op":"add","path":"/custom/scene/地点","value":"旧剧院"}'
        ']}</tavern_state>'
    )

    assert parsed.patch[0]["path"] == "/relationship/信任"
    assert parsed.patch[1]["path"] == "/scene/地点"


def test_runtime_prompt_does_not_require_invented_relationship_scores():
    from app.services.runtime.prompt import build_runtime_prompt

    text = build_runtime_prompt(
        {"mode": "relationship", "capabilities": {"relationship_state": False}},
        {"relationship": {"affection": 0, "trust": 0, "tension": 0}},
    )

    assert "不要为了填充面板而创建好感、信任、张力" in text
    assert "本轮没有可靠变化时 patch 必须为空" in text
