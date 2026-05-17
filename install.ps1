$ErrorActionPreference = "Stop"
$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Dream Studio Installer" -ForegroundColor Cyan
Write-Host "======================"

# Check Python version
function Get-PythonCmd {
    foreach ($cmd in @("py", "python3", "python")) {
        try {
            $version = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($version) {
                $parts = $version.Split(".")
                if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 12) {
                    return $cmd
                }
            }
        } catch {}
    }
    return $null
}

$Python = Get-PythonCmd

if (-not $Python) {
    Write-Host "Python 3.12+ not found. Attempting install via winget..."
    try {
        winget install Python.Python.3.12 --silent
        $Python = "py"
    } catch {
        Write-Host "ERROR: Could not install Python automatically." -ForegroundColor Red
        Write-Host "Please install Python 3.12+ from https://python.org"
        Write-Host "Then run this script again."
        exit 1
    }
}

Write-Host "Using Python: $Python"

# Run Dream Studio installer
Write-Host ""
Write-Host "Installing Dream Studio..."
Set-Location $RepoDir
& $Python -m interfaces.cli.ds integrate install claude_code --execute

# Report
Write-Host ""
Write-Host "Running health check..."
& $Python -m interfaces.cli.ds doctor

Write-Host ""
Write-Host "Dream Studio installed." -ForegroundColor Green
Write-Host "Restart PowerShell or run: . `$PROFILE"
Write-Host "Then type: ds doctor"
