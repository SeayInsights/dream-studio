# install.ps1 — dream-studio Windows setup
# Checks execution policy, then delegates to scripts/setup.py
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found. Install Python 3.11+ from https://python.org/downloads/"
    exit 1
}
py scripts/setup.py
exit $LASTEXITCODE
