# AI Tavern Lite - Start Script (PowerShell)
$ErrorActionPreference = "Continue"
# Paths are resolved from PSScriptRoot; keep the caller's working directory unchanged.

$appUrl = "http://127.0.0.1:8000"
$healthUrl = "$appUrl/api/health"
$pythonExe = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"
$helper = Join-Path $PSScriptRoot "scripts\open_when_ready.ps1"
$managedDataDir = if ($env:AI_TAVERN_DATA_DIR) {
    $env:AI_TAVERN_DATA_DIR
} elseif ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "AI-Tavern-Lite\data"
} else {
    Join-Path $HOME "AppData\Local\AI-Tavern-Lite\data"
}

if (-not (Test-Path $pythonExe)) {
    Write-Host "[错误] 未找到虚拟环境解释器：$pythonExe" -ForegroundColor Red
    Write-Host "请先运行 setup.ps1，或手动创建 backend\.venv。"
    Read-Host "按回车退出"
    exit 1
}

if (-not (Test-Path (Join-Path $PSScriptRoot "frontend\dist\index.html"))) {
    Write-Host "[警告] 未找到前端构建产物，将以 API-only 模式启动。" -ForegroundColor Yellow
    Write-Host ""
}

try {
    $existing = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 2
    if ($existing.status -eq "ok") {
        Write-Host "AI Tavern 已经在运行，正在打开浏览器..." -ForegroundColor Green
        Start-Process $appUrl
        exit 0
    }
}
catch {
    # No healthy existing instance; continue with startup.
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Tavern Lite 启动中..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "服务地址: $appUrl"
Write-Host "用户数据目录: $managedDataDir"
Write-Host "浏览器会在健康检查通过后自动打开。"
Write-Host "按 Ctrl+C 停止服务。"
Write-Host ""

$helperArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$helper`" -HealthUrl `"$healthUrl`" -AppUrl `"$appUrl`" -TimeoutSeconds 45"
Start-Process -FilePath "powershell.exe" -ArgumentList $helperArgs -WindowStyle Hidden | Out-Null

Push-Location (Join-Path $PSScriptRoot "backend")
try {
    & $pythonExe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    $serverExit = $LASTEXITCODE
}
finally {
    Pop-Location
}

Write-Host ""
if ($serverExit -ne 0) {
    Write-Host "[错误] 后端启动失败，退出代码：$serverExit" -ForegroundColor Red
    Write-Host "请保留本窗口中的报错，或查看 $managedDataDir\logs\app.log。"
}
else {
    Write-Host "服务已停止。"
}
Read-Host "按回车退出"
exit $serverExit
