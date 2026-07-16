# AI Tavern 诊断与健康检查

## 打开诊断面板

启动程序后进入：

`设置 → 开发者与诊断`

页面会检查：

- 后端服务
- 数据库
- 前端构建
- 模型配置
- 沉浸状态引擎
- 日志目录写入权限

模型配置显示“需检查”时：

- 如果正在使用 Mock 模式，这是正常的；
- 如果已经关闭 Mock，请确认 Base URL、API Key 和 Model ID 都已填写。

## 最近一次请求

完成一轮聊天后点击“刷新”，可以看到：

- 请求编号
- 完成状态
- 首字延迟和总耗时
- Prompt Token 估算
- 世界书触发数量
- 历史消息裁剪数量
- 流式分片数量
- 状态更新与解析错误数量

这些指标只记录数量和状态，不记录聊天正文。

## 一键导出诊断包

点击“一键导出诊断包”，浏览器会下载：

`ai-tavern-diagnostics-日期-时间.zip`

将这个 ZIP 直接发给排查人员即可。压缩包通常包含：

- `health.json`
- `system.json`
- `settings-sanitized.json`
- `database-summary.json`
- `latest-request.json`
- 脱敏后的日志尾部

## 隐私边界

默认诊断包不会包含：

- 完整 API Key
- Authorization 或自定义请求头的值
- 完整 Prompt
- 完整聊天正文
- 角色卡正文
- 世界书正文

Base URL 会删除账号信息、查询参数与 URL 片段。API Key 只保留掩码和末尾四位。

## 本地日志

日志位于：

`backend/data/logs/`

- `app.log`：应用运行日志，单文件最大 10 MB，保留 5 个轮转文件。
- `chat-YYYY-MM-DD.jsonl`：每轮模型请求的结构化摘要，保留 7 天。

“清空诊断日志”不会删除角色、会话或聊天记录。
