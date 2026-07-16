# Windows 启动热修

本热修解决 `start.bat` 在后端尚未完成初始化时就打开浏览器，导致首次页面显示“无法访问”的问题。

新的启动流程：

1. 检查 `backend\.venv\Scripts\python.exe` 是否存在。
2. 检查是否已有健康实例运行。
3. 启动后端并轮询 `/api/health`。
4. 健康检查通过后才打开浏览器。
5. 启动失败时保留窗口、退出代码和日志位置。

若仍无法启动，请在项目根目录打开 CMD 后运行：

```bat
start.bat
```

并保留窗口中从 `[错误]` 开始的内容，或发送：

```text
backend\data\logs\app.log
```
