@echo off
REM dream-studio hook launcher (Windows cmd).
REM
REM Usage: run.cmd <handler-name> [args...]
REM
REM Resolves the plugin root, picks a Python interpreter, and searches
REM runtime\hooks\{pack}\ for the named handler. Falls back to the legacy
REM hooks\handlers\ path during migration.

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"

if "%~1"=="" (
    >&2 echo usage: run.cmd ^<handler-name^> [args...]
    exit /b 2
)

set "HANDLER=%~1"
shift

if defined CLAUDE_PLUGIN_ROOT (
    set "PLUGIN_ROOT=%CLAUDE_PLUGIN_ROOT%"
) else (
    if exist "!SCRIPT_DIR!runtime\hooks" (
        pushd "!SCRIPT_DIR!." >nul 2>nul || (
            >&2 echo run.cmd: could not resolve plugin root from !SCRIPT_DIR!.
            exit /b 5
        )
    ) else (
        pushd "!SCRIPT_DIR!.." >nul 2>nul || (
            >&2 echo run.cmd: could not resolve plugin root from !SCRIPT_DIR!..
            exit /b 5
        )
    )
    set "PLUGIN_ROOT=!CD!"
    popd >nul
)
if defined DREAM_STUDIO_HOOK_DEBUG (
    >&2 echo run.cmd: script dir: !SCRIPT_DIR!
    >&2 echo run.cmd: plugin root: !PLUGIN_ROOT!
)

REM Resolution order is explicit, not a filesystem glob — first match wins.
set "HANDLER_PATH="
for %%K in (core quality career analyze domains meta) do (
    if "!HANDLER_PATH!"=="" (
        if defined DREAM_STUDIO_HOOK_DEBUG (
            >&2 echo run.cmd: checking !PLUGIN_ROOT!\runtime\hooks\%%K\!HANDLER!.py
        )
        if exist "!PLUGIN_ROOT!\runtime\hooks\%%K\!HANDLER!.py" (
            set "HANDLER_PATH=!PLUGIN_ROOT!\runtime\hooks\%%K\!HANDLER!.py"
        )
    )
)
if "!HANDLER_PATH!"=="" (
    if exist "!PLUGIN_ROOT!\hooks\handlers\!HANDLER!.py" (
        set "HANDLER_PATH=!PLUGIN_ROOT!\hooks\handlers\!HANDLER!.py"
    )
)
if "!HANDLER_PATH!"=="" (
    >&2 echo run.cmd: handler not found: !HANDLER!
    exit /b 3
)

REM Prefer version-pinned py launcher, then fall back.
set "PYTHON="
where py.exe >nul 2>nul && (
    py -3.12 -c "pass" >nul 2>nul && set "PYTHON=py -3.12" || (
        py -3.11 -c "pass" >nul 2>nul && set "PYTHON=py -3.11" || (
            set "PYTHON=py"
        )
    )
)
if not defined PYTHON (
    for %%P in (python3.exe python.exe) do (
        if "!PYTHON!"=="" (
            where %%P >nul 2>nul && set "PYTHON=%%P"
        )
    )
)
if "!PYTHON!"=="" (
    >&2 echo run.cmd: no Python interpreter found on PATH ^(tried: py -3.12, py -3.11, py, python3, python^)
    exit /b 4
)

set "CLAUDE_PLUGIN_ROOT=!PLUGIN_ROOT!"
set "PYTHONPATH=!PLUGIN_ROOT!;!PLUGIN_ROOT!\hooks;!PYTHONPATH!"

REM Collect remaining args after the handler name
set "ARGS="
:collect_args
if "%~1"=="" goto run
set "ARGS=%ARGS% %1"
shift
goto collect_args

:run
%PYTHON% "!HANDLER_PATH!"%ARGS%
exit /b %ERRORLEVEL%
