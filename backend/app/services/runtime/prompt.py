from __future__ import annotations

import json


def build_runtime_prompt(profile: dict | None, state: dict | None) -> str:
    """Build the machine-readable runtime contract injected into the system prompt."""
    profile = profile if isinstance(profile, dict) else {}
    state = state if isinstance(state, dict) else {}
    mode = str(profile.get("mode", state.get("mode", "relationship")))
    capabilities = profile.get("capabilities", {}) if isinstance(profile.get("capabilities"), dict) else {}
    compact_state = json.dumps(state, ensure_ascii=False, separators=(",", ":"))

    feature_lines = []
    if capabilities.get("dice"):
        feature_lines.append("- 发生检定时可额外输出卡片约定的 <dice> 区块，平台会转为原生骰子卡。")
    if capabilities.get("battle_check"):
        feature_lines.append("- 发生战斗检定时可额外输出 <battlecheck> 区块。")
    if capabilities.get("battle"):
        feature_lines.append("- 仅在战斗进行中输出 <battle> 快照；探索和日常阶段不要输出。")
    feature_text = "\n".join(feature_lines)

    return f"""【沉浸运行时】
体验模式：{mode}
当前机器状态（只依据剧情中真实发生的变化更新）：
{compact_state}

回复要求：
1. 正文先写自然、连贯、符合角色卡的叙事；不要把机器状态 JSON 写进正文。
2. 不要输出 HTML、CSS、JavaScript、iframe 或远程脚本。平台会渲染原生状态栏。
3. 回复末尾必须追加且只追加一个隐藏状态块，使用严格 JSON：
<tavern_state>
{{"patch":[],"events":[],"choices":[],"dice":[],"battle_checks":[],"battle":null,"expression":""}}
</tavern_state>
4. patch 只记录本轮确实发生的变化。支持 replace、add、insert、increment、delta、remove。
5. events 写 0-4 条已经发生的重要事件；choices 写 0-4 个符合当前情境、不会替用户强行决定的下一步行动。
6. 角色卡已有的变量协议和字段名优先；不要为了填充面板而创建好感、信任、张力或任务数值。
7. 只有叙事中已经明确发生的事实才能写入 patch，并在 events 中用自然语言说明原因；本轮没有可靠变化时 patch 必须为空。
8. 场景地点、时间、环境、人物状态发生明确变化时，应更新现有对应字段；不要用“平静”“正常”等占位值覆盖未知状态。
9. expression 写当前最适合角色的简短表情或情绪。
{feature_text}
""".strip()
