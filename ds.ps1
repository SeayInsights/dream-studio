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

# WHICH PYTHON, and why each is asked before the next.
#
# An interpreter is chosen only if it RUNS. Checking that a name exists is not enough: on a
# stock Windows box `python` is the Microsoft Store App Execution Alias, a stub that prints
# "Python was not found" and exits 9009 -- Get-Command finds it all the same.
#
#   1. $env:DS_PYTHON, when set -- an explicit choice outranks every guess.
#   2. `python` on PATH, when it runs -- the interpreter the operator gets by typing
#      `python`, and so the one Dream Studio's requirements were installed into.
#   3. `py -3` -- the launcher's default is the newest Python INSTALLED, not the one in use.
#      Asked first, it picked a Python with no dependencies on any machine holding two of
#      them: a GitHub Windows runner, where setup-python's interpreter is on PATH and the
#      launcher's default is another, failed `import jsonschema` before the CLI started.
#   4. `python3`.
function Test-Python([string[]]$Command) {
    try {
        $exe = $Command[0]
        $rest = @($Command | Select-Object -Skip 1)
        & $exe @rest -c "import sys; sys.exit(0)" *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$PythonCmd = $null
$candidates = @()
if ($env:DS_PYTHON) { $candidates += , @($env:DS_PYTHON) }
$candidates += , @("python")
$candidates += , @("py", "-3")
$candidates += , @("python3")
foreach ($candidate in $candidates) {
    if ((Get-Command $candidate[0] -ErrorAction SilentlyContinue) -and (Test-Python $candidate)) {
        $PythonCmd = $candidate
        break
    }
}
if (-not $PythonCmd) {
    Write-Error "No working Python found (a Microsoft Store alias stub does not count). Install Python 3.12+ and retry, or set DS_PYTHON."
    exit 1
}

$exe = $PythonCmd[0]
$rest = @($PythonCmd | Select-Object -Skip 1)
& $exe @rest $Cli --source-root $RepoRoot @args
exit $LASTEXITCODE
