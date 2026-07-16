# AI Tavern Lite Stability and Security Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 修复 AI Tavern Lite 已确认的聊天一致性、设置持久化、数据库路径和发布安全问题，并建立真实接口回归测试。

**Architecture:** 保留 FastAPI + SQLAlchemy + React/Zustand 结构，以结构化 SSE 事件作为前后端聊天状态的单一事实来源。后端负责消息 ID、序号和最终状态；前端只做乐观展示并在服务端事件到达后对齐。设置覆盖规则改为“显式环境变量 > 数据库 > 默认值”。

**Tech Stack:** Python 3.11+、FastAPI、SQLAlchemy、Pydantic v2、pytest、React 18、TypeScript、Zustand、Vite。

## Global Constraints

- 不改变现有 API 路径。
- 不新增运行时依赖。
- 不在交付包中包含数据库、API Key、聊天记录、备份、node_modules 或缓存。
- 任何修复先写失败测试，再写最小实现。
- 对旧 SQLite 数据库保持可启动；新约束不依赖自动迁移才能保证 API 删除行为正确。

---

### Task 1: 聊天 Prompt 与 SSE 状态协议

**Files:**
- Modify: `backend/app/api/chat.py`
- Modify: `backend/app/services/prompt_builder/builder.py`
- Modify: `backend/app/services/llm/provider.py`
- Test: `backend/tests/test_chat_flow.py`

**Interfaces:**
- Produces: SSE `message`, `content`, `done`, `error` 事件；`done.status` 为 `complete|stopped|error`。
- Produces: `LLMProvider.cancelled: bool` 只读属性。

- [x] 编写真实 `/api/chat/stream` 测试，断言用户消息在 provider Prompt 中只出现一次。
- [x] 运行目标测试并确认因重复消息失败。
- [x] 调整构建顺序：保存用户消息后，PromptBuilder 仅从 `messages` 读取当前消息，不再额外追加 `user_message`。
- [x] 增加 SSE `message` 事件，包含服务端创建的用户消息和助手消息。
- [x] 增加 provider `cancelled` 属性，并在生成循环结束后根据取消状态写入 `stopped` 或 `complete`。
- [x] 增加 SSE `done` 事件并运行目标测试。

### Task 2: 重新生成与会话活跃时间

**Files:**
- Modify: `backend/app/api/chat.py`
- Modify: `backend/app/api/sessions.py`
- Test: `backend/tests/test_chat_flow.py`

**Interfaces:**
- `/api/chat/regenerate` 删除最后一条助手消息并返回新的流。
- 新增、编辑、删除消息均更新 `ChatSession.updated_at`。

- [x] 编写重新生成测试，断言数据库最终只有一条对应助手回复。
- [x] 编写会话更新时间测试。
- [x] 运行测试并确认失败。
- [x] 在聊天流创建消息、完成、停止和错误时 touch 会话。
- [x] 在消息增删改接口 touch 会话，并运行目标测试。

### Task 3: 设置覆盖规则、密钥清除与参数验证

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/services/settings_service.py`
- Modify: `backend/app/schemas/__init__.py`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Test: `backend/tests/test_settings.py`

**Interfaces:**
- `SettingsService.get_all_settings()` 仅使用 `model_fields_set` 中显式配置的环境字段覆盖数据库。
- `SettingsUpdate` 使用 Pydantic 范围约束及跨字段校验。

- [x] 编写 provider_name、username 持久化和 clear_api_key 测试。
- [x] 编写非法 temperature/top_p/token 配置返回 422 的测试。
- [x] 运行测试并确认失败。
- [x] 修复覆盖与清除逻辑，加入跨字段验证。
- [x] 设置页加入“清除已保存 API Key”按钮并运行测试与 TypeScript 构建。

### Task 4: 数据库路径、序号与记忆删除一致性

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/db/models.py`
- Modify: `backend/app/api/sessions.py`
- Modify: `backend/app/api/memory.py`
- Test: `backend/tests/test_data_integrity.py`

**Interfaces:**
- 默认 `database_url` 为基于 `base_dir/data/ai_tavern.db` 的绝对 SQLite URL。
- 新数据库包含 `UniqueConstraint("session_id", "sequence")`。
- 删除会话显式删除其 session memories，兼容无外键的旧数据库。

- [x] 编写从不同 cwd 导入配置时数据库路径不变的测试。
- [x] 编写删除会话同时删除 session memory 的 API 测试。
- [x] 编写客户端 sequence 被忽略且服务端递增的测试。
- [x] 运行测试并确认失败。
- [x] 实现绝对路径、模型约束和 API 删除/序号逻辑。
- [x] 运行目标测试。

### Task 5: 前端流状态同步

**Files:**
- Modify: `frontend/src/api/index.ts`
- Modify: `frontend/src/stores/appStore.ts`
- Modify: `frontend/src/types/index.ts`

**Interfaces:**
- `streamChat(options)` 回调接收 `onMessage`, `onChunk`, `onDone`, `onError`。
- `regenerate()` 使用同一 SSE 解析器。

- [x] 删除未使用的 EventSource。
- [x] 抽出 POST SSE 解析器，支持 chat 和 regenerate。
- [x] 发送时先加入临时用户消息；收到 `message` 后用服务端消息替换临时项并设置真实 generatingMessageId。
- [x] `done` 更新助手消息最终状态；`error` 更新为 error；停止更新为 stopped。
- [x] regenerate 调用 `/chat/regenerate`，不再仅删除前端数组。
- [x] 运行 `npm run build`。

### Task 6: 发布包清理与最终验证

**Files:**
- Modify: `.gitignore`
- Modify: `setup.bat`
- Modify: `setup.ps1`
- Modify: `README.md`

**Interfaces:**
- 安装脚本始终使用 lockfile 干净安装并在失败时返回失败状态。

- [x] 修正忽略规则与安装脚本。
- [x] 删除工作副本中的数据库、备份、缓存、node_modules、dist、pycache、pytest cache 和 tmp 文件。
- [x] 运行后端完整 pytest。
- [x] 执行前端 `npm ci` 与 `npm run build`。
- [x] 扫描交付目录，确认无数据库、密钥、node_modules、缓存和备份。
- [x] 生成新的脱敏 ZIP。
