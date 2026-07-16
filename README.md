# AI Tavern 2.1 Preview

> 当前版本：`2.2.0-preview.1`。本版加入通用 Tavern Compatibility Core：MVU 初始变量、路径映射、安全宏、状态栏投影、旧会话补齐和运行级兼容报告。

轻量级本地角色卡运行平台：将角色卡、世界书、关系状态与冒险状态组合成可持续推进的沉浸式世界。


## 一键自检

双击 `run-self-test.bat`，程序会在端口 8765 启动隔离测试实例，自动检查后端、SSE、状态持久化、Persona、群聊、剧情分支、Prompt 预算，以及浏览器端的设置返回、会话缓存、草稿/滚动位置、动态数据和说话人颜色。结果保存在 `self-test-results/ai-tavern-self-test-*.zip`，可直接上传用于排障。测试不会修改现有数据库、角色、聊天记录或 API Key。


## 2.1 Preview 核心能力

- ✅ **聊天工作区常驻**：设置和记忆页以覆盖层打开，返回聊天不会卸载消息列表。
- ✅ **会话缓存恢复**：消息、运行时、时间线、草稿和滚动位置按会话缓存并后台刷新。
- ✅ **消息 AST**：将旁白、动作、思考和具名对白拆分为结构化片段。
- ✅ **多角色彩色对白**：同名角色在整个会话中使用稳定颜色，卡片可声明安全颜色映射。
- ✅ **通用动态数据**：未知变量不再丢弃，会自动显示为数值、标签、对象或列表。
- ✅ **每轮状态变化**：回复下方可展开查看本轮变量路径、写入值和被拒绝的补丁。
- ✅ **卡片兼容报告**：展示 V2/V3、世界书、Regex、MVU、骰子、战斗和未知扩展的支持情况。
- ✅ **声明式 UI Manifest**：卡片可请求安全的进度条、标签、键值表与状态网格，不执行任意脚本。
- ✅ **Persona、群聊与剧情分支**：可创建玩家身份、多角色编组，并保存或恢复剧情节点。
- ✅ **Prompt 规划器**：世界书和角色设定都有预算，最近对话不会再被可选条目全部挤掉。
- ✅ **诊断系统保留**：健康检查、请求指标与一键导出诊断包继续可用。

完整说明见 [`AI_TAVERN_2_PREVIEW.md`](AI_TAVERN_2_PREVIEW.md)。

## 项目介绍

AI Tavern Lite 支持导入 Tavern/SillyTavern 风格角色卡，连接任意 OpenAI 兼容模型，并为每个会话维护独立的场景、关系、冒险、事件与战斗状态。模型正文与隐藏状态分离，用户的行动会形成可见、可回滚、能影响后续回复的持续世界。

## 功能列表

## 沉浸式运行时

- ✅ 每个会话拥有独立、角色卡驱动的状态；平台不再自动创建好感、信任、张力或任务数值
- ✅ 只有角色卡协议或剧情补丁真正写入的数据才会显示，空面板自动隐藏
- ✅ 模型结构化输出：正文、状态补丁、事件、行动选项和表情相互分离
- ✅ 重新生成、删除最新回复和剧情回滚会同步恢复状态
- ✅ 本轮世界书触发可视化
- ✅ 原生骰子卡片、战斗检定与只读战斗地图快照
- ✅ D&D / 冒险卡原生角色创建器
- ✅ 兼容 MVU `UpdateVariable/JSONPatch` 的安全子集
- ✅ 卡片 HTML、CSS 与 JavaScript 不会执行

详细协议和开发说明见 [`IMMERSIVE_RUNTIME.md`](IMMERSIVE_RUNTIME.md)。

### 已实现

- ✅ **角色卡导入**：支持 PNG 和 JSON 格式
  - Tavern V2 格式兼容
  - Character Card V2 / V3 格式兼容
  - PNG 内嵌 Base64 JSON 解析
  - 中文角色名和特殊字符支持

- ✅ **角色管理**
  - 角色列表、搜索
  - 角色详情查看
  - 角色编辑（保留未知扩展字段）
  - 角色删除（级联清理相关数据）
  - 角色 JSON 导出

- ✅ **聊天系统**
  - 多会话独立管理
  - 流式输出（SSE）
  - 停止生成
  - 重新生成最后一条回复
  - 编辑消息
  - 删除单条消息
  - 聊天记录自动保存
  - Markdown 安全渲染
  - 会话导出

- ✅ **世界书 / Lorebook**
  - 常驻条目自动加载
  - 关键词触发条目
  - 正则关键词支持
  - 启用/禁用控制
  - 按插入顺序排序
  - 内容去重

- ✅ **长期记忆**
  - SQLite 存储，无需向量数据库
  - 手动添加/编辑/删除
  - 重要度权重
  - 关键词匹配检索
  - 分类管理
  - 可选自动提取（默认关闭）

- ✅ **Prompt 构建**
  - 分层 Prompt 构建
  - 模板变量替换（{{char}}、{{user}}）
  - 上下文预算自动裁剪
  - 最少保留最近 8 条消息
  - Prompt 预览（显示各部分 Token 估算）

- ✅ **模型服务**
  - OpenAI 兼容接口
  - 可配置 Base URL、API Key、Model ID
  - 可配置 Temperature、Top P、Max Tokens、上下文长度
  - 自定义请求头
  - 连接测试功能
  - Mock 模式（无需 API Key 即可测试）

- ✅ **安全特性**
  - API Key 前端掩码显示
  - 日志不输出 API Key
  - 默认监听 127.0.0.1
  - 文件上传大小限制
  - Markdown XSS 防护

- ✅ **界面**
  - 深色主题
  - 响应式布局
  - 左侧边栏导航
  - 角色详情
  - 设置页面
  - 记忆管理页面

### 当前暂不支持

- ❌ TTS 语音
- ❌ 语音识别
- ❌ 图片生成
- ❌ 任意第三方脚本 / 插件直接执行（Regex、MVU 与状态栏采用安全兼容层）
- ❌ 云端账户
- ❌ 多用户登录
- ❌ 向量数据库

## 界面结构

```text
┌──────────────┬──────────────────────────────┬──────────────────┐
│ 角色与会话    │ 沉浸式剧情舞台                │ 世界状态          │
│ 搜索 / 导入   │ 场景目标、角色回复、事件卡片   │ 场景与表情        │
│ 会话列表      │ 骰子、检定、战斗快照           │ 关系或角色属性    │
│ 记忆 / 设置   │ 动态行动选项与输入框            │ 世界书与剧情回滚  │
└──────────────┴──────────────────────────────┴──────────────────┘
```

## 环境要求

- **Python**: 3.11 或更高版本
- **Node.js**: 22.12 或更高版本
- **操作系统**: Windows 10/11（已测试），理论支持 macOS/Linux


> [!IMPORTANT]
> 发布或分享源码前，请确认压缩包中不包含 `backend/data/`、`.env`、`node_modules/`、`frontend/dist/` 或任何数据库备份。API Key 与聊天记录都存放在运行数据库中。

## Windows 最简单安装方法

### 方式一：一键安装（推荐）

1. 打开项目文件夹
2. 双击运行 `setup.bat`
3. 等待安装完成
4. 双击 `start.bat` 启动程序

如果缺少 Python 或 Node.js，脚本会提示安装命令：
```
winget install Python.Python.3.11
winget install OpenJS.NodeJS.LTS
```

### 方式二：PowerShell 安装

```powershell
# 在项目目录下执行
.\setup.ps1
.\start.ps1
```

## 手动安装方法

### 1. 后端安装

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

### 2. 前端安装

```bash
cd frontend
npm ci
npm run build
```

### 3. 启动

```bash
# 正式模式（后端提供静态文件）
cd backend
.venv\Scripts\activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

开发模式（前后端分离）：
```bash
# 终端1：后端
cd backend
.venv\Scripts\activate
python -m uvicorn app.main:app --reload

# 终端2：前端
cd frontend
npm run dev
```

## 模型接口配置

### DeepSeek / OpenAI 兼容接口配置

1. 启动程序后点击左侧「设置」
2. 关闭「Mock 模式」开关
3. 填写以下信息：
   - **服务商名称**：自定义名称，如 "DeepSeek"
   - **Base URL**：接口地址，如 `https://api.deepseek.com`
   - **API Key**：你的 API 密钥
   - **Model ID**：模型名称，如 `deepseek-chat`
4. 点击「测试连接」验证配置
5. 点击「保存设置」

> **注意**：Model ID 请以实际服务商提供的名称为准，不要假设模型名称。
> Base URL 末尾有无 `/v1` 均可，程序会自动处理。

### Mock 模式使用方法

默认开启 Mock 模式，无需任何配置即可体验完整功能：
- 导入角色卡
- 创建对话
- 发送消息（会收到 Mock 测试回复）
- 测试所有界面功能

适合首次安装验证、界面演示和离线开发使用。

## 角色卡导入方法

### JSON 角色卡
1. 点击侧边栏角色区域的上传图标
2. 选择 `.json` 格式的角色卡文件
3. 导入成功后会自动选中该角色

### PNG 角色卡
1. 同上，选择 `.png` 格式的角色卡图片
2. 程序会自动读取 PNG 元数据中的角色信息
3. 头像会自动保存

支持的角色卡格式：
- Tavern V2 JSON
- Character Card V2
- Character Card V3（含 data 字段）
- PNG 内嵌 tEXt/iTXt 元数据

## 数据存放位置

所有运行数据都保存在项目目录下的 `backend/data/` 文件夹中：

```
backend/data/
├── ai_tavern.db      # SQLite 数据库（角色、会话、消息、记忆、设置）
├── avatars/          # 角色头像图片
├── backups/          # 数据库自动备份（保留最近 5 份）
├── characters/       # 预留
└── exports/          # 预留
```

## 备份方法

1. 直接复制整个 `data/` 文件夹即可完整备份
2. 程序每次启动会自动在 `data/backups/` 创建数据库备份
3. 如需迁移，复制整个 `backend/data/` 目录到新位置即可

## 常见问题

### Node / npm 命令不存在？

安装 Node.js LTS：
```
winget install OpenJS.NodeJS.LTS
```
或从 https://nodejs.org/ 下载安装包。

### python 命令不存在？

安装 Python 3.11+：
```
winget install Python.Python.3.11
```
安装时请勾选 "Add Python to PATH"。

### 端口 8000 被占用？

修改后端启动命令，使用其他端口：
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

### API 连接失败怎么办？

1. 检查 Base URL 是否正确
2. 检查 API Key 是否有效
3. 检查网络连接是否正常
4. 确认模型名称是否正确（不同服务商命名不同）
5. 点击「测试连接」查看具体错误信息

### 如何彻底卸载但保留数据？

1. 删除 `backend/.venv/` 虚拟环境
2. 删除 `frontend/node_modules/` 和 `frontend/dist/`
3. `backend/data/` 文件夹保留即可，所有用户数据都在里面

## 运行测试

### 后端测试

```bash
cd backend
.venv\Scripts\activate
python -m pytest
```

测试覆盖：
- 健康检查
- 数据库初始化
- V2/V3 角色卡解析
- PNG 角色卡解析
- 中文角色名
- Lorebook 触发规则
- Prompt 构建与裁剪
- 会话与消息
- Mock 流式输出
- API Key 安全
- 级联删除
- 会话状态、状态补丁与回滚
- D&D 骰子、战斗检定和战斗快照解析
- 生成中止不应用半截状态

### 前端构建检查

```bash
cd frontend
npm run build
```

## 技术栈

**后端**
- Python 3.11+
- FastAPI + Uvicorn
- SQLAlchemy 2.x + SQLite
- Pydantic 2.x
- OpenAI Python SDK
- Pillow（PNG 解析）

**前端**
- React 18 + TypeScript
- Vite
- Tailwind CSS
- Zustand（状态管理）
- React Router
- React Markdown + rehype-sanitize
- Lucide React（图标）

## 当前限制

1. 第一版仅支持单用户本地使用
2. 长期记忆使用关键词匹配，未使用向量检索
3. 自动记忆提取为简单规则实现，效果有限
4. 不支持群聊、语音、图片生成等高级功能
5. 角色卡中的 JavaScript、HTML 替换和远程脚本不会执行（设计如此，保障安全）
6. 战斗地图目前为只读快照，不是完整虚拟桌面或规则裁判
7. 当前界面尚未提供角色编辑/导出、会话重命名/导出和世界书编辑入口；相应后端接口仍可直接调用

## License

MIT

## 诊断与健康检查

1. 打开“设置 → 开发者与诊断”。
2. 点击“刷新”查看后端、数据库、前端、模型、状态引擎和日志目录状态。
3. 完成一轮聊天后查看首字延迟、Prompt 估算、世界书、历史裁剪和状态补丁结果。
4. 点击“一键导出诊断包”，将下载的 ZIP 用于问题排查。

诊断系统默认不记录完整聊天、完整 Prompt、角色卡正文、API Key 或自定义请求头值。详细说明见 `DIAGNOSTICS.md`。

## 生产服务器部署（P0 加固版）

公网部署请使用根目录的 `compose.yaml`，不要直接开放 Uvicorn 的 8000 端口。完整说明见 [`SECURITY_P0.md`](SECURITY_P0.md)。

```bash
cp .env.production.example .env.production
# 修改域名、至少 12 位随机访问密码，以及可选模型环境变量
docker compose --env-file .env.production up -d --build
```

生产配置会强制单用户登录、可信 Host、API/模型限流、请求体限制和 SSRF 防护，并关闭 API 文档、诊断、自检和网页端模型设置写入。当前 SQLite 与停止生成状态仍要求 `--workers 1` 和单应用副本。
