# AI Tavern 2.2.0 Preview.1 — Tavern Compatibility Core

本版不为单张角色卡添加专用代码，而是增加通用的 SillyTavern/Tavern Helper 安全兼容层。

## 通用兼容能力

- 从 `tavern_helper.variables.stat_data` 或关闭的 `[initvar]` 世界书条目初始化会话变量。
- 将角色卡自定义 JSON Pointer 安全映射到 `/custom`，支持 `replace`、`add`、`remove`。
- 将常见时间、地点、关系、好感、状态、情绪字段投影到玩家面板，原始变量仍完整保留。
- 支持 `<user>`、`<char>`、`{{getvar::...}}`、`{{format_message_variable::stat_data}}`。
- 安全解释常见的 `getvar + if/else + getwi` 只读模板，不执行任意 EJS、STscript 或 JavaScript。
- 将 `<StatusPlaceHolderImpl/>` 转换为原生状态组件；外部脚本和原卡 HTML/事件处理器保持隔离。
- 世界书按角色核心、运行协议和普通世界设定分类，避免复杂卡只注入变量协议而丢失人设。
- 旧会话会补齐新识别的默认变量，同时保留已经游玩产生的数值和物品。
- 兼容报告新增运行级检查：初始化来源、更新路径、宏、状态栏投影和脚本隔离。

## 安全边界

- 不加载角色卡声明的外部 JavaScript。
- 不执行任意 Tavern Helper、EJS、STscript 或 HTML 事件。
- 未识别扩展与原始卡片数据继续保留，便于后续兼容。
