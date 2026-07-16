param(
    [switch]$SkipNpmCi
)

$ErrorActionPreference = "Stop"
$initialLocation = (Get-Location).Path

function Write-Step {
    param([string]$Message)

    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Pass {
    param([string]$Message)

    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Assert-LastExitCode {
    param([string]$Operation)

    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE."
    }
}

function Assert-Condition {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

try {
    $root = $PSScriptRoot
    Push-Location $root

    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " AI Tavern Lite - Release Verification" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    Write-Step "Checking required project files"

    $requiredFiles = @(
        "setup.ps1",
        "start.ps1",
        "backend\requirements.txt",
        "backend\pytest.ini",
        "frontend\package.json",
        "frontend\package-lock.json"
    )

    foreach ($relativePath in $requiredFiles) {
        Assert-Condition `
            (Test-Path (Join-Path $root $relativePath)) `
            "Required file is missing: $relativePath"
    }

    Write-Pass "Required project files exist"

    Write-Step "Checking Python virtual environment"

    $venvPython = Join-Path $root "backend\.venv\Scripts\python.exe"

    Assert-Condition `
        (Test-Path $venvPython) `
        "Python virtual environment is missing. Run setup.ps1 first."

    $pythonVersion = (
        & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
    ).Trim()

    Assert-LastExitCode "Python version check"

    Assert-Condition `
        $pythonVersion.StartsWith("3.11.") `
        "Python 3.11 is required, but the virtual environment uses Python $pythonVersion."

    Write-Pass "Python $pythonVersion"

    Write-Step "Checking Node.js and npm"

    Assert-Condition `
        ([bool](Get-Command "node" -ErrorAction SilentlyContinue)) `
        "Node.js was not found."

    Assert-Condition `
        ([bool](Get-Command "npm" -ErrorAction SilentlyContinue)) `
        "npm was not found."

    $nodeVersion = (& node --version).Trim()
    Assert-LastExitCode "Node.js version check"

    & node -e "const [major,minor]=process.versions.node.split('.').map(Number); process.exit(major>22 || (major===22 && minor>=12) ? 0 : 1)"
    Assert-LastExitCode "Node.js minimum version check"

    $npmVersion = (& npm --version).Trim()
    Assert-LastExitCode "npm version check"

    Write-Pass "Node.js $nodeVersion, npm $npmVersion"

    Write-Step "Checking PowerShell scripts"

    $powerShellFiles = @()
    $powerShellFiles += Get-ChildItem `
        -Path $root `
        -Filter "*.ps1" `
        -File `
        -Force

    $scriptsDirectory = Join-Path $root "scripts"

    if (Test-Path $scriptsDirectory) {
        $powerShellFiles += Get-ChildItem `
            -Path $scriptsDirectory `
            -Filter "*.ps1" `
            -File `
            -Recurse `
            -Force
    }

    foreach ($file in $powerShellFiles) {
        $tokens = $null
        $parseErrors = $null

        [System.Management.Automation.Language.Parser]::ParseFile(
            $file.FullName,
            [ref]$tokens,
            [ref]$parseErrors
        ) | Out-Null

        if ($parseErrors.Count -gt 0) {
            $messages = (
                $parseErrors |
                ForEach-Object { $_.Message }
            ) -join "; "

            throw "PowerShell parse error in $($file.Name): $messages"
        }

        $text = [System.IO.File]::ReadAllText($file.FullName)
        $containsNonAscii = [regex]::IsMatch($text, "[^\x00-\x7F]")

        if ($containsNonAscii) {
            $bytes = [System.IO.File]::ReadAllBytes($file.FullName)

            $hasUtf8Bom = (
                $bytes.Length -ge 3 -and
                $bytes[0] -eq 239 -and
                $bytes[1] -eq 187 -and
                $bytes[2] -eq 191
            )

            Assert-Condition `
                $hasUtf8Bom `
                "PowerShell script containing non-ASCII text must use UTF-8 BOM: $($file.FullName)"
        }
    }

    Write-Pass "$($powerShellFiles.Count) PowerShell scripts parsed successfully"

    Write-Step "Checking tracked sensitive and generated files"

    if (Test-Path (Join-Path $root ".git")) {
        $trackedFiles = & git -C $root ls-files
        Assert-LastExitCode "git ls-files"

        $forbiddenPattern = (
            '(^|/)\.env$' +
            '|(^|/)(id_rsa|id_ed25519)$' +
            '|\.pem$' +
            '|\.key$' +
            '|\.p12$' +
            '|\.pfx$' +
            '|(^|/)backend/data/' +
            '|(^|/)backend/\.venv/' +
            '|(^|/)frontend/node_modules/'
        )

        $forbiddenTrackedFiles = @(
            $trackedFiles |
            Where-Object { $_ -match $forbiddenPattern }
        )

        if ($forbiddenTrackedFiles.Count -gt 0) {
            throw (
                "Sensitive or generated files are tracked by Git:`n" +
                ($forbiddenTrackedFiles -join "`n")
            )
        }

        Write-Pass "No sensitive or generated files are tracked by Git"
    }
    else {
        Write-Host "[WARN] .git directory was not found; tracked-file checks were skipped." -ForegroundColor Yellow
    }

    Write-Step "Compiling backend Python modules"

    Push-Location (Join-Path $root "backend")
    try {
        & $venvPython -m compileall -q app
        Assert-LastExitCode "Python compile check"
    }
    finally {
        Pop-Location
    }

    Write-Pass "Backend Python compilation"

    Write-Step "Running backend tests"

    Push-Location (Join-Path $root "backend")
    try {
        & $venvPython -m pytest -q
        Assert-LastExitCode "Backend tests"
    }
    finally {
        Pop-Location
    }

    Write-Pass "Backend tests"

    Write-Step "Installing and building frontend"

    Push-Location (Join-Path $root "frontend")
    try {
        if (-not $SkipNpmCi) {
            & npm ci
            Assert-LastExitCode "npm ci"
        }
        else {
            Write-Host "[SKIP] npm ci" -ForegroundColor Yellow
        }

        & npm run build
        Assert-LastExitCode "Frontend build"
    }
    finally {
        Pop-Location
    }

    Assert-Condition `
        (Test-Path (Join-Path $root "frontend\dist\index.html")) `
        "Frontend build did not produce dist\index.html."

    Write-Pass "Frontend production build"

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host " RELEASE VERIFICATION PASSED" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green

    exit 0
}
catch {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host " RELEASE VERIFICATION FAILED" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red

    exit 1
}
finally {
    while ((Get-Location).Path -ne $initialLocation) {
        try {
            Pop-Location
        }
        catch {
            Set-Location $initialLocation
            break
        }
    }
}