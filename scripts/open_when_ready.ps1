param(
    [string]$HealthUrl = "http://127.0.0.1:8000/api/health",
    [string]$AppUrl = "http://127.0.0.1:8000",
    [int]$TimeoutSeconds = 45
)

$deadline = (Get-Date).AddSeconds([Math]::Max(5, $TimeoutSeconds))
while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 2
        if ($response.status -eq "ok") {
            Start-Process $AppUrl
            exit 0
        }
    }
    catch {
        # The backend is still starting. Retry until the deadline.
    }
    Start-Sleep -Milliseconds 500
}

exit 1
