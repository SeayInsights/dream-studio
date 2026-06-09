"""
Session config reader/writer.
Written by on-session-start, read by on-context-threshold.
Stores invocation flags and session context so continuation
sessions can inherit the same runtime configuration.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

SESSION_CONFIG_PREFIX = "claude-session-config-"


def config_path(session_id: str) -> Path:
    return Path(tempfile.gettempdir()) / f"{SESSION_CONFIG_PREFIX}{session_id}.json"


def write_session_config(session_id: str, data: dict) -> None:
    """Write session config to temp. Called from on-session-start."""
    path = config_path(session_id)
    path.write_text(json.dumps(data), encoding="utf-8")


def read_session_config(session_id: str) -> dict:
    """Read session config from temp. Called from on-context-threshold."""
    path = config_path(session_id)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def spawn_new_session(claude_cmd: str, cwd: str) -> None:
    """Spawn a new Claude Code terminal window. Platform-aware."""
    import subprocess
    import tempfile
    import time

    try:
        if sys.platform == "win32":
            subprocess.Popen(
                [
                    "powershell",
                    "-NoExit",
                    "-Command",
                    f'Set-Location "{cwd}"; '
                    f'Write-Host "Dream Studio: continuing session" '
                    f"-ForegroundColor Cyan; {claude_cmd}",
                ],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                cwd=cwd,
            )
        elif sys.platform == "darwin":
            apple_script = (
                f'tell application "Terminal" to do script '
                f'"cd \\"{cwd}\\" && echo \\"Dream Studio: continuing session\\" '
                f'&& {claude_cmd}"'
            )
            subprocess.Popen(["osascript", "-e", apple_script])
        else:
            terminals = [
                [
                    "gnome-terminal",
                    "--",
                    "bash",
                    "-c",
                    f'echo "Dream Studio: continuing session"; {claude_cmd}; exec bash',
                ],
                ["xterm", "-e", f'echo "Dream Studio: continuing session"; {claude_cmd}; bash'],
                ["konsole", "--noclose", "-e", claude_cmd],
            ]
            for term in terminals:
                try:
                    subprocess.Popen(term, cwd=cwd)
                    break
                except FileNotFoundError:
                    continue
    except Exception as e:
        try:
            log = Path(tempfile.gettempdir()) / "dream-studio-spawn-error.log"
            log.write_text(f"{time.time()}: spawn failed: {e}\n", encoding="utf-8")
        except Exception:
            pass


def detect_invocation_flags() -> list[str]:
    """
    Walk the process parent chain to find the claude invocation
    and extract its command line flags.

    Known flags to detect and carry over:
    --dangerously-skip-permissions
    --model <value>
    --profile <value>
    --max-tokens <value>
    --output-format <value>
    --verbose
    --debug

    Returns a list of flag strings ready to join into a command.
    """
    flags = []
    try:
        import psutil

        proc = psutil.Process(os.getpid())
        for _ in range(5):
            parent = proc.parent()
            if parent is None:
                break
            cmdline = parent.cmdline()
            cmdline_str = " ".join(cmdline).lower()
            if "claude" in cmdline_str:
                i = 0
                while i < len(cmdline):
                    arg = cmdline[i]
                    if arg == "--dangerously-skip-permissions":
                        flags.append(arg)
                    elif arg == "--verbose":
                        flags.append(arg)
                    elif arg == "--debug":
                        flags.append(arg)
                    elif arg in (
                        "--model",
                        "--profile",
                        "--output-format",
                        "--max-tokens",
                    ) and i + 1 < len(cmdline):
                        flags.append(arg)
                        flags.append(cmdline[i + 1])
                        i += 1
                    i += 1
                break
            proc = parent
    except Exception:
        pass
    return flags
