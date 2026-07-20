# AI Tavern Lite 2.4.3 R2 Hotfix 1

## 修复目标

R2 在主回复缺失变量更新时会触发状态提取，但真实 OpenAI 兼容接口测试出现：

- `fallback_attempted = true`
- `fallback_response_characters = 0`
- `fallback_reason = fallback_failed`
- 状态没有变化

## 修复内容

1. 主剧情继续使用流式请求。
2. 状态补救创建独立 Provider 实例，不复用主剧情流对象。
3. 状态补救使用非流式 `chat.completions.create(..., stream=False)`。
4. 从完整响应的 `choices[0].message.content` 读取 JSON。
5. 保持同一 API 配置、模型和自定义请求头，但不把密钥写入提示词或诊断。
6. 空响应和失败不会修改状态，也不会增加 revision。

## 诊断分类

- `fallback_applied`
- `fallback_no_operations`
- `fallback_no_valid_operations`
- `fallback_empty_response`
- `fallback_invalid_json`
- `fallback_provider_error`
- `fallback_provider_init_error`
- `fallback_response_too_long`
- `fallback_no_targets`

新增诊断字段：

- `fallback_http_completed`
- `fallback_finish_reason`
- `fallback_response_type`
- `fallback_error_type`
- `fallback_response_characters`

## 安全边界

补救结果仍经过角色卡声明字段白名单、操作数量限制、文本长度限制、关系值单轮变化限制和状态引擎校验。模型输出不会作为代码执行。

## 数据库

不需要数据库迁移。
