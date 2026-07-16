# AI Tavern 诊断系统设计

## 目标

为 AI Tavern 增加默认安全、可导出的可观测性系统，使普通用户无需理解终端日志，也能完成健康检查并生成可分享的诊断包。

## 范围

- 结构化应用日志与聊天请求诊断
- 请求 ID、首字延迟、总耗时、模型、Mock 状态、Prompt 估算、世界书、记忆、裁剪、状态补丁与完成原因
- 健康检查 API 与设置页诊断面板
- 一键导出 ZIP 诊断包
- 日志轮转、清理与严格脱敏
- 不默认记录完整 Prompt、聊天正文、角色卡正文、API Key 或自定义请求头值

## 架构

### DiagnosticService

单例服务负责：

1. 初始化 `backend/data/logs` 与 `backend/data/diagnostics`。
2. 维护轮转文本日志和按日 JSONL 聊天日志。
3. 在内存中保存最近一次请求摘要，并同步保存为 `latest-request.json`。
4. 生成系统信息、脱敏设置、数据库数量摘要和日志尾部。
5. 将上述文件打包成临时 ZIP 并流式返回。

### 聊天埋点

每个 `/chat/stream` 请求生成短 UUID，并记录：

- 会话、用户消息、助手消息 ID
- 服务商、模型、Mock 模式
- Prompt 消息数、估算 Token、世界书与记忆数量
- 首字延迟、总耗时、流式 chunk 数
- 状态版本、应用/拒绝补丁数、解析错误数
- `complete / stopped / error` 与错误类别

SSE 的 `message`、`content`、`done`、`error` 事件携带 `request_id`，前端可关联显示。

### API

- `GET /api/diagnostics/health`
- `GET /api/diagnostics/latest`
- `POST /api/diagnostics/export`
- `DELETE /api/diagnostics/logs`

导出包只包含脱敏元数据和日志摘要。API Key 仅显示是否配置与末尾四位；Base URL 去除查询参数和用户信息；请求头不导出值。

### 前端

设置页增加“开发者与诊断”卡片：

- 后端、数据库、前端构建、模型配置、Mock、状态引擎、日志目录状态
- 最近请求摘要
- 刷新健康检查
- 一键导出诊断包
- 清空日志

浏览器通过 Blob 下载 ZIP，不需要访问本机路径。

## 日志保留

- `app.log` 使用 10 MB 轮转，保留 5 个历史文件
- 聊天 JSONL 按日存储，启动时删除 7 天以前文件
- 最近请求文件不包含正文

## 错误处理

诊断写入失败不能破坏聊天主链路；所有记录操作均捕获 I/O 错误并回退到控制台警告。导出失败返回明确 HTTP 错误。

## 测试

- 脱敏单元测试
- 健康检查 API 测试
- 导出 ZIP 内容与敏感信息扫描
- 聊天成功、停止、错误三种诊断记录测试
- 前端 TypeScript 和生产构建验证
