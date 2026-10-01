# Verify the pbiviz toolchain is set up. Print actionable fixes for anything missing.
#
# Usage: pwsh scripts/check-pbiviz-env.ps1
#
# Exit codes:
#   0  all checks passed
#   1  one or more checks failed (see stdout for fixes)

[CmdletBinding()]
param()

$failed = 0

function Test-Tool($name, $command, $minVersion = $null, $fixHint) {
    Write-Host "Checking $name..." -NoNewline
    try {
        $output = & $command 2>&1
        if ($LASTEXITCODE -ne 0) { throw "command failed: $output" }
        $version = ($output | Select-String -Pattern '\d+\.\d+(\.\d+)?' | Select-Object -First 1).Matches.Value
        if ($minVersion -and [Version]$version -lt [Version]$minVersion) {
            Write-Host " FAIL ($version, need >= $minVersion)" -ForegroundColor Red
            Write-Host "  Fix: $fixHint"
            $script:failed++
        } else {
            Write-Host " OK ($version)" -ForegroundColor Green
        }
    } catch {
        Write-Host " MISSING" -ForegroundColor Red
        Write-Host "  Fix: $fixHint"
        $script:failed++
    }
}

# Node 18+
Test-Tool -name "Node" `
          -command { node --version } `
          -minVersion "18.0" `
          -fixHint "Install Node 18+ from https://nodejs.org/ (LTS recommended)."

# pbiviz
Write-Host "Checking pbiviz CLI..." -NoNewline
try {
    $pbivizVersion = & pbiviz --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "command failed" }
    Write-Host " OK ($pbivizVersion)" -ForegroundColor Green
} catch {
    Write-Host " MISSING" -ForegroundColor Red
    Write-Host "  Fix: npm install -g powerbi-visuals-tools"
    $failed++
}

# Dev cert (PowerBI Visuals Tools cert at ~/.pbiviz/)
Write-Host "Checking pbiviz dev SSL cert..." -NoNewline
$certPath = Join-Path -Path $env:USERPROFILE -ChildPath ".pbiviz\PowerBIVisualTest_public.pfx"
if (Test-Path -LiteralPath $certPath) {
    Write-Host " OK" -ForegroundColor Green
} else {
    Write-Host " MISSING" -ForegroundColor Red
    Write-Host "  Fix: pbiviz install-cert (then approve the Windows prompt to trust the cert)"
    $failed++
}

# Power BI Desktop (informational, not failing the check if missing)
$pbiPath = "$env:ProgramFiles\Microsoft Power BI Desktop\bin\PBIDesktop.exe"
Write-Host "Checking Power BI Desktop..." -NoNewline
if (Test-Path -LiteralPath $pbiPath) {
    Write-Host " OK" -ForegroundColor Green
} else {
    Write-Host " NOT FOUND (informational)" -ForegroundColor Yellow
    Write-Host "  Note: Power BI Desktop install is needed for sideload testing but not for build."
}

Write-Host ""
if ($failed -eq 0) {
    Write-Host "All required checks passed." -ForegroundColor Green
    exit 0
} else {
    Write-Host "$failed check(s) failed -- see fixes above." -ForegroundColor Red
    exit 1
}
