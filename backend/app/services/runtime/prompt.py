from __future__ import annotations

import json

from .state_schema import schema_prompt_contract
from .state_aliases import alias_prompt_contract


def build_runtime_prompt(profile: dict | None, state: dict | None) -> str:
    """Build the machine-readable runtime contract injected into the system prompt."""
    profile = profile if isinstance(profile, dict) else {}
    state = state if isinstance(state, dict) else {}
    mode = str(profile.get("mode", state.get("mode", "relationship")))
    capabilities = profile.get("capabilities", {}) if isinstance(profile.get("capabilities"), dict) else {}
    compact_state = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    schema_contract = schema_prompt_contract(profile.get("state_schema", {}))
    alias_contract = alias_prompt_contract(profile.get("state_aliases", {}))

    feature_lines = []
    if capabilities.get("dice"):
        feature_lines.append("- 发生检定时可额外输出卡片约定的 <dice> 区块，平台会转为原生骰子卡。")
    if capabilities.get("battle_check"):
        feature_lines.append("- 发生战斗检定时可额外输出 <battlecheck> 区块。")
    if capabilities.get("battle"):
        feature_lines.append("- 仅在战斗进行中输出 <battle> 快照；探索和日常阶段不要输出。")
    if capabilities.get("text_status_protocol"):
        feature_lines.append("- 此角色卡声明了文本状态栏协议。正文之后继续按角色卡要求输出 <text>...<end> 或 <status>...</status>；其中只能包含纯文本区段和键值，不要生成 HTML、CSS、JavaScript。平台会将它安全转换为原生状态面板。")
    feature_text = "\n".join(feature_lines)

    if capabilities.get("mvu_command_protocol"):
        state_contract = """3. 此角色卡声明了 Tavern MVU 命令协议。每个完整回复末尾都必须且只能追加一个 <UpdateVariable> 区块，严格使用角色卡规定的 _.set、_.add、_.insert、_.remove。
4. 正文结束后再输出变量区块；不要把变量命令混入正文，不要同时追加平台原生状态块或第二套变量块。平台只会在本地安全解析命令，绝不会执行角色卡脚本。
5. 必须逐项检查角色卡声明的变量，只更新叙事中已经明确发生的事实，并遵守数值范围、单轮幅度和记忆条件；没有可靠变化时输出不含命令的 <UpdateVariable></UpdateVariable>。"""
        state_tail = """6. 角色卡已有的变量字段名优先；不要为了填充面板而创建新数值。
7. 场景地点、时间、人物状态发生明确变化时，应更新已有对应字段；不要用占位值覆盖未知状态。"""
    elif capabilities.get("mvu_json_patch_protocol"):
        state_contract = """3. 此角色卡声明了 <UpdateVariable><JSONPatch> 协议。严格遵循角色卡给出的 JSONPatch 格式。
4. 不要同时追加平台原生状态块或第二套变量块；平台会在本地验证并应用允许的状态操作。
5. 只更新叙事中已经明确发生的事实；没有可靠变化时输出空 patch。"""
        state_tail = """6. 角色卡已有的变量字段名优先；不要为了填充面板而创建新数值。
7. 场景地点、时间、人物状态发生明确变化时，应更新已有对应字段；不要用占位值覆盖未知状态。"""
    else:
        state_contract = """3. 回复末尾必须追加且只追加一个隐藏状态块，使用严格 JSON：
<tavern_state>
{\"patch\":[],\"events\":[],\"choices\":[],\"dice\":[],\"battle_checks\":[],\"battle\":null,\"expression\":\"\"}
</tavern_state>
4. patch 只记录本轮确实发生的变化。支持 replace、add、insert、increment、delta、remove。"""
        state_tail = """5. events 写 0-4 条已经发生的重要事件；choices 写 0-4 个符合当前情境、不会替用户强行决定的下一步行动。
6. 角色卡已有的变量协议和字段名优先；不要为了填充面板而创建好感、信任、张力或任务数值。
7. 只有叙事中已经明确发生的事实才能写入 patch，并在 events 中用自然语言说明原因；本轮没有可靠变化时 patch 必须为空。
8. 场景地点、时间、环境、人物状态发生明确变化时，应更新现有对应字段；不要用“平静”“正常”等占位值覆盖未知状态。
9. expression 写当前最适合角色的简短表情或情绪。"""

    return f"""【沉浸运行时】
体验模式：{mode}
当前机器状态（只依据剧情中真实发生的变化更新）：
{compact_state}
{schema_contract}
{alias_contract}

回复要求：
1. 正文先写自然、连贯、符合角色卡的叙事；不要把机器状态 JSON 写进正文。
2. 不要输出 HTML、CSS、JavaScript、iframe 或远程脚本。角色卡声明的纯文本状态标签不属于可执行脚本，平台会将其渲染为原生状态栏。
{state_contract}
{state_tail}
{feature_text}
""".strip()
