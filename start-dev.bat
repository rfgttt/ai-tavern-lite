@echo off
chcp 65001 >nul
title AI Tavern Lite - Dev Mode

cd /d "%~dp0"

if not exist "backend\.venv" (
    echo [错误] 未找到虚拟环境，请先运行 setup.bat 进行安装
    pause
    exit /b 1
)

echo ========================================
echo   AI Tavern Lite - 开发模式
echo ========================================
echo.
echo 后端: http://127.0.0.1:8000
echo 前端: http://127.0.0.1:5173
echo.

:: Start backend in background
cd backend
start "Backend" cmd /k ".venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

:: Start frontend
cd ..\frontend
start "Frontend" cmd /k "npm run dev"

echo 两个服务已在独立窗口中启动
echo 关闭此窗口不会停止服务
echo.
pause
