@echo off
REM dream-studio hook launcher (Windows cmd).
REM
REM Usage: run.cmd <handler-name> [args...]
REM
REM Resolves the plugin root, picks a Python interpreter, and searches
REM packs\{pack}\hooks\ for the named handler. Falls back to the legacy
REM hooks\handlers\ path during migration.

setlocal enabledelayedexpansion

if "%~1"=="" (
    echo usage: run.cmd ^<handler-name^> [args...] 1^>^&2
    exit /b 2
)

set "HANDLER=%~1"
shift

set "SCRIPT_DIR=%~dp0"
if defined CLAUDE_PLUGIN_ROOT (
    set "PLUGIN_ROOT=%CLAUDE_PLUGIN_ROOT%"
) else (
    for %%I in ("%SCRIPT_DIR%..") do set "PLUGIN_ROOT=%%~fI"
)

REM Resolution order is explicit, not a filesystem glob — first match wins.
set "HANDLER_PATH="
for %%K in (core quality career analyze domains meta) do (
    if not defined HANDLER_PATH (
        if exist "%PLUGIN_ROOT%\packs\%%K\hooks\%HANDLER%.py" (
            set "HANDLER_PATH=%PLUGIN_ROOT%\packs\%%K\hooks\%HANDLER%.py"
        )
    )
)
if not defined HANDLER_PATH (
    if exist "%PLUGIN_ROOT%\hooks\handlers\%HANDLER%.py" (
        set "HANDLER_PATH=%PLUGIN_ROOT%\hooks\handlers\%HANDLER%.py"
    )
)
if not defined HANDLER_PATH (
    echo run.cmd: handler not found: %HANDLER% 1^>^&2
    exit /b 3
)

set "PYTHON="
for %%P in (py.exe python3.exe python.exe) do (
    if not defined PYTHON (
        where %%P >nul 2>nul && set "PYTHON=%%P"
    )
)
if not defined PYTHON (
    echo run.cmd: no Python interpreter found on PATH ^(tried: py, python3, python^) 1^>^&2
    exit /b 4
)

set "CLAUDE_PLUGIN_ROOT=%PLUGIN_ROOT%"
set "PYTHONPATH=%PLUGIN_ROOT%\hooks;%PYTHONPATH%"

REM Collect remaining args after the handler name
set "ARGS="
:collect_args
if "%~1"=="" goto run
set "ARGS=%ARGS% %1"
shift
goto collect_args

:run
"%PYTHON%" "%HANDLER_PATH%"%ARGS%
exit /b %ERRORLEVEL%
