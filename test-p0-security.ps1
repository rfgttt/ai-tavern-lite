param(
  [string]$BaseUrl = "https://localhost",
  [string]$Username = "admin",
  [Parameter(Mandatory=$true)][string]$Password,
  [switch]$TestRateLimit,
  [switch]$SkipPytest
)
$ErrorActionPreference = "Stop"
$argsList = @("scripts/test_p0_security.py", "--base-url", $BaseUrl, "--username", $Username, "--password", $Password)
if ($TestRateLimit) { $argsList += "--test-rate-limit" }
if ($SkipPytest) { $argsList += "--skip-pytest" }
python @argsList
exit $LASTEXITCODE
