@echo off
setlocal
chcp 65001 >nul
title AI Tavern Lite

cd /d "%~dp0"

set "APP_URL=http://127.0.0.1:8000"
set "HEALTH_URL=http://127.0.0.1:8000/api/health"
set "PYTHON_EXE=backend\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [错误] 未找到虚拟环境解释器：%PYTHON_EXE%
    echo 请先运行 setup.bat，或按手动安装说明创建 backend\.venv。
    pause
    exit /b 1
)

if not exist "frontend\dist\index.html" (
    echo [警告] 未找到前端构建产物，将以 API-only 模式启动。
    echo 如需完整界面，请先在 frontend 目录运行 npm install 和 npm run build。
    echo.
)

:: If an instance is already healthy, open it instead of starting a second server.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-RestMethod -Uri '%HEALTH_URL%' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 } } catch {}; exit 1" >nul 2>nul
if not errorlevel 1 (
    echo AI Tavern 已经在运行，正在打开浏览器...
    start "" "%APP_URL%"
    exit /b 0
)

echo ========================================
echo   AI Tavern Lite 启动中...
echo ========================================
echo.
echo 服务地址: %APP_URL%
echo 浏览器会在健康检查通过后自动打开。
echo 按 Ctrl+C 停止服务。
echo.

:: Poll the health endpoint in the background. This prevents the browser from
:: opening before Uvicorn has finished database and diagnostics initialization.
start "" /b powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\open_when_ready.ps1" -HealthUrl "%HEALTH_URL%" -AppUrl "%APP_URL%" -TimeoutSeconds 45

cd /d "%~dp0backend"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
set "SERVER_EXIT=%ERRORLEVEL%"

echo.
if not "%SERVER_EXIT%"=="0" (
    echo [错误] 后端启动失败，退出代码：%SERVER_EXIT%
    echo 请保留本窗口中的报错，或查看 backend\data\logs\app.log。
) else (
    echo 服务已停止。
)
pause
exit /b %SERVER_EXIT%
