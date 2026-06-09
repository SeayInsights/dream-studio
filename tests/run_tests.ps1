# WARNING: Do not run this script as a single
# command from an AI tool call. It will timeout
# and kill the session.
#
# For AI tool calls: run each directory
# separately, one pytest call per tool use.
#
# For local developer use: run normally with
#   powershell -File tests/run_tests.ps1

# Canonical test runner — runs each directory in isolation to prevent OOM.
# Usage: powershell -File tests/run_tests.ps1
# Never run: py -m pytest tests/unit/ directly (causes exit 137 OOM).

$dirs = @(
    "tests/unit/emitters",
    "tests/unit/canonical",
    "tests/unit/integrations",
    "tests/unit/hooks",
    "tests/unit/spool"
)
$failed = @()
foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) { continue }
    Write-Host "Running $dir..." -ForegroundColor Cyan
    py -m pytest $dir -q --tb=short
    if ($LASTEXITCODE -ne 0) {
        $failed += $dir
    }
}
if ($failed.Count -gt 0) {
    Write-Host "FAILED: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "ALL PASSED" -ForegroundColor Green
