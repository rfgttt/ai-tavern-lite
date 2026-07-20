# Tavern MVU Compatibility 2.4.3

本阶段针对不执行第三方脚本的安全运行模式，补齐常见 Tavern Helper / MVU 角色卡的原生兼容链路。

## 支持范围

- `[InitVar]` 条目中的安全 JSON 对象与既有 YAML 子集；
- MVU `[值, 描述]` 数据结构及 `$__META_EXTENSIBLE__$` 标记；
- `stat_data.角色.字段[0]` 数组路径读取；
- `{{get_message_variable::stat_data}}` 与既有只读变量宏；
- 常见 `getvar`、数值条件分支和 `getwi` 阶段控制器；
- `<UpdateVariable>` 中的 `_.set`、`_.add`、`_.insert`、`_.remove`；
- 自定义好感、恐惧、依赖等百分制字段的 0–100 限制；
- 角色卡初始关系、伤势、重要记忆和自定义变量的原生展示；
- 角色卡 `talkativeness` 转换为安全的回复篇幅指导；
- 运行时配置版本升级，已有会话补入新识别的初始变量，同时保留已经发生的剧情进度。

## 安全边界

- 不执行角色卡 JavaScript、任意 EJS、Regex 替换输出或远程脚本；可识别意图仅转换为声明式原生组件；
- EJS 仅解释允许的只读 `getvar` / 条件 / `getwi` 子集；
- MVU 命令仅被解析为受约束的状态操作，不使用 `eval`；
- `<Analysis>` 中出现的命令文本不会被当作状态更新；
- 未知根路径仍被限制在 `/custom`；
- 禁止原型污染字段、私有字段、超深路径和超大状态。

## 协议选择

当角色卡明确声明 MVU 命令或 JSONPatch 协议时，Prompt 只要求该卡片协议，不再同时要求平台原生 `<tavern_state>`，避免模型在两套格式之间摇摆。普通角色卡继续使用平台原生状态块。

## 用户可见结果

角色卡原有的 HTML/JavaScript 状态栏不会执行，但其可识别数据会显示在原生状态面板，包括：

- 日期、时间、地点；
- 好感、害怕值、依赖值；
- 身上的伤；
- 重要记忆；
- 其他经过清理的角色卡变量。

角色卡内部“重要记忆”属于会话运行时状态，与 AI Tavern 的独立长期记忆库是两套数据；本阶段修复前者，长期记忆提取策略将在后续阶段单独改进。

## R2 状态补救

真实模型漏写 `<UpdateVariable>` 时的单次受限补救、空 patch 版本语义和诊断字段，见 [`TAVERN_MVU_RECOVERY_2.4.3_R2.md`](TAVERN_MVU_RECOVERY_2.4.3_R2.md)。


## Hotfix 3 安全原生还原

可识别的 Regex/Tavern Helper 意图现在会在删除执行源码前转换为安全清单。状态栏、Prompt 历史隐藏、记忆分页、自动变量补救、初始变量恢复和时间线操作由平台自身实现。角色卡声明的关系数值每轮/每日上限、最终锁定和阶段标签由统一状态策略强制执行。详见 [`TAVERN_SAFE_EMULATION_2.4.3_HOTFIX3.md`](TAVERN_SAFE_EMULATION_2.4.3_HOTFIX3.md)。
