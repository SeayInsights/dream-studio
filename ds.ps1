# Dream Studio global command launcher.
#
# Put the Dream Studio source root on PATH, or invoke this file directly from
# any directory. It delegates to the canonical Python CLI with an explicit
# source root so normal use does not depend on the caller's current directory.

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Cli = Join-Path $RepoRoot "interfaces\cli\ds.py"
if (-not (Test-Path $Cli)) {
    Write-Error "Dream Studio CLI not found at $Cli"
    exit 1
}

$PythonCmd = $null
foreach ($candidate in @("py", "python3", "python")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $PythonCmd = $candidate
        break
    }
}
if (-not $PythonCmd) {
    Write-Error "Python not found. Install Python 3.11+ and retry."
    exit 1
}

if ($PythonCmd -eq "py") {
    py -3 $Cli --source-root $RepoRoot @args
} else {
    & $PythonCmd $Cli --source-root $RepoRoot @args
}
exit $LASTEXITCODE
