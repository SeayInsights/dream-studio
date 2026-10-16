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

# Install Python dependencies
Write-Host ""
Write-Host "Installing Python dependencies..."
Set-Location $RepoDir
& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install failed. See output above." -ForegroundColor Red
    exit 1
}

# Install Dream Studio into its home as a versioned app (it creates or migrates the
# authority) and its Claude Code integration into one config root. Run again to upgrade.
$DsHome = "$env:USERPROFILE\.dream-studio"
$ConfigRoot = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { "$env:USERPROFILE\.claude" }
Write-Host ""
Write-Host "Installing Dream Studio into $DsHome (Claude Code root: $ConfigRoot)..."
& $Python -m interfaces.cli.ds self-install --config-root "$ConfigRoot" --execute
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: ds self-install failed. See output above." -ForegroundColor Red
    exit 1
}

# Report, from the installed app
Write-Host ""
Write-Host "Running health check..."
& "$DsHome\bin\ds.cmd" doctor

Write-Host ""
Write-Host "Dream Studio installed." -ForegroundColor Green
Write-Host "Add $DsHome\bin to PATH (see INSTALL.md), then type: ds doctor"
