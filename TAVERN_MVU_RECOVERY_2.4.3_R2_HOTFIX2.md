# AI Tavern Lite 2.4.3 R2 Hotfix 2

## 修复目标

R2 Hotfix 1 已将状态补救改为独立非流式请求，但真实 DeepSeek V4 测试仍出现：

- HTTP 请求完成；
- 返回类型为 `ChatCompletion`；
- `finish_reason = length`；
- 最终 `message.content` 为空；
- 角色状态未变化。

该形态说明状态提取的短输出预算可能被模型推理阶段耗尽，最终 JSON 尚未生成。

## 请求策略

仅当以下条件同时成立时使用 DeepSeek 专用策略：

- Base URL 的规范化主机名严格等于 `api.deepseek.com`；
- Model ID 以 `deepseek-v4` 开头。

命中后，状态补救请求使用：

- 独立 Provider；
- `stream = false`；
- `thinking.type = disabled`；
- `temperature = 0`；
- 不发送 `top_p`；
- `max_tokens = 1024`。

其他 OpenAI-compatible Provider 保持标准非流式请求，不接收 DeepSeek 专属参数。第三方网关即使使用 `deepseek-v4-*` 模型名，也不会仅凭模型名收到 `thinking` 参数。

## 响应处理

只有最终 `message.content` 可以进入 JSON 解析和状态白名单验证。

`reasoning_content`：

- 不作为状态数据；
- 不解析；
- 不执行；
- 不保存原文；
- 只记录字符数和 token 数用于诊断。

任何 `finish_reason = length` 的结果均不会应用，以避免使用截断 JSON。

## 诊断增强

新增字段：

- `fallback_reasoning_characters`
- `fallback_reasoning_tokens`
- `fallback_completion_tokens`
- `fallback_requested_max_tokens`
- `fallback_request_profile`

新增或细化原因：

- `fallback_reasoning_budget_exhausted`
- `fallback_output_truncated`
- `fallback_content_filtered`
- `fallback_upstream_resource_interrupted`

请求策略取值：

- `deepseek_non_thinking`
- `generic_nonstream`
- `mock_nonstream`

诊断不记录 API Key、自定义认证头、完整状态提取 Prompt 或 reasoning 原文。

## Prompt 收敛

状态提取仍只包含本轮必要数据，并进一步限制：

- 角色卡变量规则最多 4000 字符；
- 本轮角色回复最多 4000 字符；
- 本轮用户消息最多 1500 字符；
- 允许字段仍来自当前角色卡已声明状态。

Prompt 同时提供空操作和单项更新 JSON 示例，但不启用 `response_format=json_object`，以减少本次根因修复中的额外兼容变量。

## 安全与费用边界

- 每轮最多一次补救请求；
- 主回复已有状态操作时不触发；
- 停止、失败和中断回复不触发或不应用；
- 非法路径、未知字段、越界数值和过长内容继续由本地校验拒绝；
- 空响应、截断响应和 Provider 错误不会增加 revision；
- 不需要数据库迁移。
