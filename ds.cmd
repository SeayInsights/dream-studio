@echo off
setlocal

set "RepoRoot=%~dp0"
if "%RepoRoot:~-1%"=="\" set "RepoRoot=%RepoRoot:~0,-1%"
set "Cli=%RepoRoot%\interfaces\cli\ds.py"

if not exist "%Cli%" (
  echo Dream Studio CLI not found at %Cli% >&2
  exit /b 1
)

rem WHICH PYTHON. A candidate is used only if it RUNS: on a stock Windows box `python`
rem is the Microsoft Store alias stub, which `where` finds and which exits 9009. Order:
rem DS_PYTHON when set; `python` on PATH, the interpreter in use; `py -3`, whose default
rem is the newest Python INSTALLED rather than the one holding the requirements; python3.
rem Every call goes through CALL, because a .bat run without it never returns here.
set "PYEXE="
set "PYARGS="
if defined DS_PYTHON call :probe "%DS_PYTHON%" && (set "PYEXE=%DS_PYTHON%" & goto run)
call :probe python && (set "PYEXE=python" & goto run)
call :probe py -3 && (set "PYEXE=py" & set "PYARGS=-3" & goto run)
call :probe python3 && (set "PYEXE=python3" & goto run)

echo No working Python found (a Microsoft Store alias stub does not count). Install Python 3.12+ and retry, or set DS_PYTHON. >&2
exit /b 1

:run
call "%PYEXE%" %PYARGS% "%Cli%" --source-root "%RepoRoot%" %*
exit /b %ERRORLEVEL%

:probe
call %* -c "import sys; sys.exit(0)" >nul 2>nul
exit /b %ERRORLEVEL%
