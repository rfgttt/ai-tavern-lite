# AI Tavern Lite - Setup Script (PowerShell)
$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Tavern Lite - 一键安装脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
Write-Host "[1/6] 检查 Python 3.11 环境..." -ForegroundColor Yellow

$pythonCmd = $null
$pythonArgs = @()

if (Get-Command "py" -ErrorAction SilentlyContinue) {
    & py -3.11 --version *> $null

    if ($LASTEXITCODE -eq 0) {
        $pythonCmd = "py"
        $pythonArgs = @("-3.11")
    }
}

if (-not $pythonCmd -and (Get-Command "python" -ErrorAction SilentlyContinue)) {
    $systemPythonVersion = (
        & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    ).Trim()

    if ($LASTEXITCODE -eq 0 -and $systemPythonVersion -eq "3.11") {
        $pythonCmd = "python"
        $pythonArgs = @()
    }
}

if (-not $pythonCmd) {
    Write-Host "[错误] 未找到 Python 3.11。" -ForegroundColor Red
    Write-Host "安装命令: winget install Python.Python.3.11"
    Read-Host "按回车退出"
    exit 1
}

& $pythonCmd @pythonArgs --version
Write-Host "Python 3.11 检查通过" -ForegroundColor Green
Write-Host ""
# Check Node.js
Write-Host "[2/6] 检查 Node.js 环境..." -ForegroundColor Yellow
try {
    node --version
    npm --version
} catch {
    Write-Host "[错误] 未找到 Node.js，请先安装 Node.js LTS" -ForegroundColor Red
    Write-Host "安装命令: winget install OpenJS.NodeJS.LTS"
    Read-Host "按回车退出"
    exit 1
}
node -e "const [major,minor]=process.versions.node.split('.').map(Number); process.exit(major>22 || (major===22 && minor>=12) ? 0 : 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 当前前端工具链需要 Node.js 22.12 或更高版本" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}
Write-Host "Node.js 检查通过" -ForegroundColor Green
Write-Host ""

# Set location
Set-Location $PSScriptRoot

# Create venv
Write-Host "[3/6] 创建 Python 虚拟环境..." -ForegroundColor Yellow

$venvPath = "backend\.venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$createVenv = -not (Test-Path $venvPython)

if (-not $createVenv) {
    $venvVersion = (
        & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    ).Trim()

    if ($LASTEXITCODE -ne 0 -or $venvVersion -ne "3.11") {
        Write-Host "检测到非 Python 3.11 虚拟环境，正在重新创建..." -ForegroundColor Yellow
        Remove-Item $venvPath -Recurse -Force
        $createVenv = $true
    }
}

if ($createVenv) {
    & $pythonCmd @pythonArgs -m venv $venvPath

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[错误] Python 虚拟环境创建失败" -ForegroundColor Red
        Read-Host "按回车退出"
        exit 1
    }

    Write-Host "Python 3.11 虚拟环境创建完成" -ForegroundColor Green
}
else {
    Write-Host "Python 3.11 虚拟环境已存在" -ForegroundColor Green
}

& $venvPython --version
Write-Host ""
# Install backend deps
Write-Host "[4/6] 安装后端依赖..." -ForegroundColor Yellow
& "backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 后端依赖安装失败" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}
Write-Host "后端依赖安装完成" -ForegroundColor Green
Write-Host ""

# Frontend
Write-Host "[5/6] 干净安装前端依赖并构建..." -ForegroundColor Yellow
Set-Location frontend
npm ci
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 前端依赖安装失败" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

Write-Host "检查前端测试类型..." -ForegroundColor Yellow
npm run test:typecheck
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 前端测试类型检查失败" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

Write-Host "运行前端测试..." -ForegroundColor Yellow
npm run test:run
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 前端测试未通过" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

Write-Host "构建前端..." -ForegroundColor Yellow
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 前端构建失败" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}
Write-Host "前端构建完成" -ForegroundColor Green
Set-Location ..
Write-Host ""

# Tests
Write-Host "[6/6] 运行后端测试..." -ForegroundColor Yellow
Set-Location backend
& ".venv\Scripts\python.exe" -m pytest
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[错误] 后端测试未通过，安装已中止" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}
Write-Host "所有测试通过" -ForegroundColor Green
Set-Location ..
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  安装完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "启动方式:"
Write-Host "  双击 start.bat  启动正式版（推荐）"
Write-Host "  双击 start-dev.bat  启动开发版"
Write-Host ""
Write-Host "默认使用 Mock 模式，无需 API Key 即可体验"
Write-Host ""
Read-Host "按回车退出"
