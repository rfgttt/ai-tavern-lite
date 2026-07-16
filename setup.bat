@echo off
chcp 65001 >nul
echo ========================================
echo   AI Tavern Lite - 一键安装脚本
echo ========================================
echo.

:: Check Python
echo [1/6] 检查 Python 环境...
where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% neq 0 (
        echo [错误] 未找到 Python，请先安装 Python 3.10+
        echo 安装命令: winget install Python.Python.3.12
        echo 或从 https://www.python.org/downloads/ 下载安装
        pause
        exit /b 1
    ) else (
        set PYTHON_CMD=py
    )
) else (
    set PYTHON_CMD=python
)

%PYTHON_CMD% --version
echo Python 检查通过
echo.

:: Check Node.js
echo [2/6] 检查 Node.js 环境...
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未找到 Node.js，请先安装 Node.js LTS
    echo 安装命令: winget install OpenJS.NodeJS.LTS
    echo 或从 https://nodejs.org/ 下载安装
    pause
    exit /b 1
)
node --version
npm --version
node -e "const [major,minor]=process.versions.node.split('.').map(Number); process.exit(major>22 || (major===22 && minor>=12) ? 0 : 1)"
if %errorlevel% neq 0 (
    echo [错误] 当前前端工具链需要 Node.js 22.12 或更高版本
    pause
    exit /b 1
)
echo Node.js 检查通过
echo.

:: Create virtual environment
echo [3/6] 创建 Python 虚拟环境...
cd /d "%~dp0"
if not exist "backend\.venv" (
    %PYTHON_CMD% -m venv backend\.venv
    echo 虚拟环境创建完成
) else (
    echo 虚拟环境已存在
)
echo.

:: Install backend dependencies
echo [4/6] 安装后端依赖...
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if %errorlevel% neq 0 (
    echo [错误] 后端依赖安装失败
    pause
    exit /b 1
)
echo 后端依赖安装完成
echo.

:: Install frontend dependencies
echo [5/6] 干净安装前端依赖并构建...
cd frontend
call npm ci
if %errorlevel% neq 0 (
    echo [错误] 前端依赖安装失败
    pause
    exit /b 1
)

echo 构建前端...
call npm run build
if %errorlevel% neq 0 (
    echo [错误] 前端构建失败
    pause
    exit /b 1
)
echo 前端构建完成
cd ..
echo.

:: Run backend tests
echo [6/6] 运行后端测试...
cd backend
.venv\Scripts\python.exe -m pytest
if %errorlevel% neq 0 (
    echo.
    echo [错误] 后端测试未通过，安装已中止
    pause
    exit /b 1
)
echo 所有测试通过
cd ..
echo.

echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 启动方式:
echo   双击 start.bat 启动正式版
echo   双击 start-dev.bat 启动开发版
echo.
echo 默认使用 Mock 模式，无需 API Key 即可体验
echo 如需配置真实模型，请在设置页面中填写接口信息
echo.
pause
