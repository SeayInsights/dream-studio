"""Platform detection and profile persistence.

Detects OS, shell, Python version, and terminal at install/doctor time.
Profile is persisted to ~/.dream-studio/state/platform.json and read by
callers that need shell-correct output or environment-aware diagnostics.
"""

from __future__ import annotations

import json
import logging
import os
import platform as _platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PLATFORM_PROFILE_ENV = "DS_PLATFORM_PROFILE_PATH"


@dataclass(frozen=True)
class PlatformProfile:
    os_name: str  # "Windows", "Linux", "Darwin"
    os_version: str  # e.g. "10.0.22631"
    shell: str  # "powershell", "cmd", "bash", "zsh", "fish", "unknown"
    python_version: str  # e.g. "3.12.8"
    terminal: str  # "Windows Terminal", "iTerm2", "gnome-terminal", "unknown"
    is_windows: bool
    is_macos: bool
    is_linux: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _detect_shell() -> str:
    """Best-effort shell detection. Returns lowercase shell name or 'unknown'."""
    # PowerShell sets PSModulePath in its environment
    if os.environ.get("PSModulePath"):
        if os.environ.get("POWERSHELL_DISTRIBUTION_CHANNEL"):
            return "powershell-core"
        return "powershell"
    # cmd sets COMSPEC to cmd.exe on Windows
    if sys.platform == "win32":
        comspec = os.environ.get("COMSPEC", "").lower()
        if "cmd.exe" in comspec:
            return "cmd"
    # Unix shells expose SHELL env var
    shell_env = os.environ.get("SHELL", "")
    if shell_env:
        shell_name = Path(shell_env).name.lower()
        if shell_name in ("bash", "zsh", "fish", "sh", "dash", "ksh"):
            return shell_name
    return "unknown"


def _detect_terminal() -> str:
    """Best-effort terminal detection. Returns terminal name or 'unknown'."""
    # Windows Terminal sets WT_SESSION
    if os.environ.get("WT_SESSION"):
        return "Windows Terminal"
    # iTerm2 sets ITERM_SESSION_ID
    if os.environ.get("ITERM_SESSION_ID"):
        return "iTerm2"
    # GNOME Terminal, Konsole, etc. set TERM_PROGRAM
    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program:
        return term_program
    # Fallback to TERM
    term = os.environ.get("TERM", "")
    if term:
        return term
    return "unknown"


def detect_platform() -> PlatformProfile:
    """Detect the current platform profile. Pure function, no side effects."""
    os_name = _platform.system()
    return PlatformProfile(
        os_name=os_name,
        os_version=_platform.version(),
        shell=_detect_shell(),
        python_version=_platform.python_version(),
        terminal=_detect_terminal(),
        is_windows=os_name == "Windows",
        is_macos=os_name == "Darwin",
        is_linux=os_name == "Linux",
    )


def _default_profile_path() -> Path:
    """Return the canonical platform profile path."""
    override = os.environ.get(PLATFORM_PROFILE_ENV)
    if override:
        return Path(override)
    return Path.home() / ".dream-studio" / "state" / "platform.json"


def ensure_platform_recorded(profile_path: Optional[Path] = None) -> PlatformProfile:
    """Detect and persist platform profile. Idempotent. Returns the profile.

    Called at install and ds doctor. Overwrites on each call so the profile
    stays current (shell switches, OS upgrades, etc.).
    """
    profile = detect_platform()
    path = profile_path if profile_path is not None else _default_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
    logger.info(f"Platform profile recorded at {path}: {profile.os_name} / {profile.shell}")
    return profile


def get_platform_profile(profile_path: Optional[Path] = None) -> PlatformProfile:
    """Read recorded platform profile. If not present, detect and record."""
    path = profile_path if profile_path is not None else _default_profile_path()
    if not path.is_file():
        return ensure_platform_recorded(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PlatformProfile(**data)
    except (json.JSONDecodeError, TypeError, OSError) as e:
        logger.warning(f"Failed to read platform profile at {path}: {e}; redetecting")
        return ensure_platform_recorded(path)


def is_windows() -> bool:
    return get_platform_profile().is_windows


def get_shell() -> str:
    return get_platform_profile().shell


def shell_syntax_hint(operation: str) -> str:
    """Return shell-correct syntax for a common operation.

    operation values: 'set_env', 'delete_files', 'chain_and', 'redirect'
    """
    shell = get_shell()
    hints = {
        "set_env": {
            "cmd": "set VAR=value",
            "powershell": "$env:VAR = 'value'",
            "powershell-core": "$env:VAR = 'value'",
            "bash": "export VAR=value",
            "zsh": "export VAR=value",
        },
        "delete_files": {
            "cmd": "del file1.txt file2.txt",
            "powershell": "Remove-Item file1.txt, file2.txt",
            "powershell-core": "Remove-Item file1.txt, file2.txt",
            "bash": "rm file1.txt file2.txt",
            "zsh": "rm file1.txt file2.txt",
        },
        "chain_and": {
            "cmd": "cmd1 && cmd2",
            "powershell": "cmd1; if ($?) { cmd2 }",
            "powershell-core": "cmd1 && cmd2",
            "bash": "cmd1 && cmd2",
            "zsh": "cmd1 && cmd2",
        },
        "redirect": {
            "cmd": "cmd > file.txt 2>&1",
            "powershell": "cmd | Out-File -Encoding utf8 file.txt",
            "powershell-core": "cmd | Out-File -Encoding utf8 file.txt",
            "bash": "cmd > file.txt 2>&1",
            "zsh": "cmd > file.txt 2>&1",
        },
    }
    return hints.get(operation, {}).get(
        shell, f"# unknown shell '{shell}' for operation '{operation}'"
    )
