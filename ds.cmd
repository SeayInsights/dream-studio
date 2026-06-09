@echo off
setlocal

set "RepoRoot=%~dp0"
if "%RepoRoot:~-1%"=="\" set "RepoRoot=%RepoRoot:~0,-1%"
set "Cli=%RepoRoot%\interfaces\cli\ds.py"

if not exist "%Cli%" (
  echo Dream Studio CLI not found at %Cli% >&2
  exit /b 1
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 "%Cli%" --source-root "%RepoRoot%" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python "%Cli%" --source-root "%RepoRoot%" %*
  exit /b %ERRORLEVEL%
)

echo Python 3.12+ was not found on PATH. >&2
exit /b 1
