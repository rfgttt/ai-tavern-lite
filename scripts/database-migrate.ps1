param(
    [ValidateSet("status", "upgrade", "validate", "history", "heads")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python 虚拟环境不存在，请先运行 setup.ps1。"
}

Push-Location (Join-Path $root "backend")
try {
    & $python -m app.db.migration_cli $Action
    if ($LASTEXITCODE -ne 0) {
        throw "数据库迁移命令失败，退出代码: $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
