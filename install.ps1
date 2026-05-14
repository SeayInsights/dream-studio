# install.ps1 — dream-studio Windows setup
# Validates environment, then delegates to interfaces/cli/setup.py

$ErrorActionPreference = "Stop"

# --- Repo-root validation ---------------------------------------------------
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Canonical = Join-Path $RepoRoot "interfaces" "cli" "setup.py"
if (-not (Test-Path $Canonical)) {
    Write-Error "install.ps1 must be run from the dream-studio repo root. Expected: $Canonical"
    exit 1
}

# --- Python presence ---------------------------------------------------------
$PythonCmd = $null
foreach ($candidate in @("py", "python3", "python")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $PythonCmd = $candidate
        break
    }
}
if (-not $PythonCmd) {
    Write-Error "Python not found. Install Python 3.11+ from https://python.org/downloads/"
    exit 1
}

# --- Python version >= 3.11 --------------------------------------------------
$VersionArgs = if ($PythonCmd -eq "py") { @("-3", "-c") } else { @("-c") }
try {
    $VersionOutput = & $PythonCmd @VersionArgs "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>&1
    $Parts = $VersionOutput.Trim().Split(".")
    $Major = [int]$Parts[0]
    $Minor = [int]$Parts[1]
    if ($Major -lt 3 -or ($Major -eq 3 -and $Minor -lt 11)) {
        Write-Error "Python >= 3.11 required (found $Major.$Minor). Update from https://python.org/downloads/"
        exit 1
    }
} catch {
    Write-Error "Failed to determine Python version. Ensure Python 3.11+ is installed and on PATH."
    exit 1
}

# --- Delegate to canonical setup ---------------------------------------------
if ($PythonCmd -eq "py") {
    py -3 $Canonical @args
} else {
    & $PythonCmd $Canonical @args
}
exit $LASTEXITCODE
