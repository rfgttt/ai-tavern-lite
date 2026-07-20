# 公开仓库截图清单

建议最终保留 5～7 张截图。不要堆大量相似页面。

## 必需截图

### 1. 首页与聊天工作区

应展示：

- 左侧角色与会话；
- 中间消息区；
- 右侧运行时状态；
- 不包含私人聊天和 API Key。

建议文件名：

```text
docs/assets/01-chat-workspace.png
```

### 2. 角色编辑与备用开场白

应展示：

- 角色基本信息；
- 开场白标签页；
- 多个备用开场和预览；
- 固定底部操作区。

```text
docs/assets/02-character-editor.png
```

### 3. 新会话向导

应展示：

- 单人/多人；
- Persona；
- 开场白来源；
- 初始状态；
- 不要展示过长私人角色描述。

```text
docs/assets/03-session-wizard.png
```

### 4. 运行时与时间线

应展示：

- 当前状态；
- 本轮变化；
- 时间线或回滚入口。

```text
docs/assets/04-runtime-timeline.png
```

### 5. 自动验证结果

截取：

```text
312 passed
79 passed
RELEASE VERIFICATION PASSED
```

```text
docs/assets/05-release-verification.png
```

### 6. 数据库迁移状态

截取：

```text
Current revision: 20260720_0003
Head revision:    20260720_0003
Status:           up to date
```

```text
docs/assets/06-database-migration.png
```

### 7. Git 提交历史

展示阶段性提交，不需要展示所有 hash：

```text
modularize frontend application store
extract backend chat orchestrator
add Alembic database migrations
harden session and stream reliability
```

```text
docs/assets/07-git-history.png
```

## 截图规则

- 统一使用 16:9 或相近比例；
- 截图前关闭系统通知；
- 不显示本机用户名、API Key、`.env`、真实数据库和私人对话；
- 角色头像和素材必须确认可公开使用；
- 保持同一浏览器主题和缩放；
- 图片宽度建议 1400～1920 像素；
- PNG 用于界面和终端，必要时压缩；
- README 中每张图写一句说明，不重复功能清单。

## 录屏规则

- 使用演示数据；
- 先录 Mock，真实 API 只录短回复；
- 剪掉安装和等待时间；
- 鼠标移动放慢；
- 加简单字幕，不需要复杂特效；
- 不使用有版权风险的背景音乐。
