$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host '[ERROR] Missing backend\.venv\Scripts\python.exe' -ForegroundColor Red
    Write-Host 'Create the backend virtual environment first.'
    Read-Host 'Press Enter to exit'
    exit 1
}
$env:PYTHONUTF8 = '1'
& $python (Join-Path $PSScriptRoot 'scripts\self_test_runner.py')
$code = $LASTEXITCODE
if ($code -eq 0) {
    Write-Host '[OK] All self-tests passed.' -ForegroundColor Green
} else {
    Write-Host '[WARN] Self-test found one or more problems. Upload the newest ZIP from self-test-results.' -ForegroundColor Yellow
}
Read-Host 'Press Enter to exit'
exit $code
