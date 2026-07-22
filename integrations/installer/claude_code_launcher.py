"""PATH profile management, global launcher scripts, first-run guide, and
version marker resolution for the Claude Code installer.

WO-GF-CONTROL-INSTALL-split: see claude_code.py facade docstring.
"""

from __future__ import annotations

import platform
import stat
import sys
from pathlib import Path
from typing import Any

from .claude_code_shared import _DS_ENTRY, _DS_PATH_MARKER


def _write_path_to_profile(bin_dir: Path) -> dict[str, Any]:
    """Append ~/.dream-studio/bin to PATH in the platform shell profile. Idempotent."""
    system = platform.system()
    path_line: str

    if system == "Windows":
        try:
            _sp = __import__("subprocess")
            raw = _sp.run(
                ["powershell", "-Command", "$PROFILE"],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
            profile_path = Path(raw) if raw else None
        except Exception:
            profile_path = None
        if not profile_path:
            profile_path = (
                Path.home() / "Documents" / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"
            )
        path_line = '$env:PATH += ";$HOME\\.dream-studio\\bin"'
    elif system == "Darwin":
        profile_path = Path.home() / ".zshrc"
        path_line = 'export PATH="$HOME/.dream-studio/bin:$PATH"'
    else:
        profile_path = Path.home() / ".bashrc"
        path_line = 'export PATH="$HOME/.dream-studio/bin:$PATH"'

    profile_path.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if profile_path.is_file():
        try:
            existing = profile_path.read_text(encoding="utf-8")
        except Exception:
            pass

    if _DS_PATH_MARKER in existing:
        return {"profile": str(profile_path), "action": "skipped", "reason": "already_present"}

    try:
        with profile_path.open("a", encoding="utf-8") as f:
            f.write(f"\n{_DS_PATH_MARKER}\n{path_line}\n")
        return {"profile": str(profile_path), "action": "appended"}
    except Exception as exc:
        return {"profile": str(profile_path), "action": "failed", "error": str(exc)}


def _write_global_launcher(*, ds_home: Path) -> dict[str, Any]:
    """Write ds.cmd (Windows) or ds (Unix) to ~/.dream-studio/bin/."""
    bin_dir = ds_home / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    is_windows = platform.system() == "Windows"
    entry_path = str(_DS_ENTRY)

    if is_windows:
        launcher_path = bin_dir / "ds.cmd"
        launcher_content = f'@echo off\npy "{entry_path}" %*\n'
        launcher_path.write_text(launcher_content, encoding="utf-8")
    else:
        launcher_path = bin_dir / "ds"
        launcher_content = f'#!/bin/sh\n{sys.executable} "{entry_path}" "$@"\n'
        launcher_path.write_text(launcher_content, encoding="utf-8")
        launcher_path.chmod(
            launcher_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
        )

    path_result = _write_path_to_profile(bin_dir)

    if path_result["action"] == "appended":
        path_instructions = (
            f"\nDS CLI installed to: {launcher_path}\n"
            f"PATH configured in: {path_result['profile']}\n"
            "Restart your terminal or source the profile file, then run `ds` from anywhere."
        )
    elif path_result["action"] == "skipped":
        path_instructions = (
            f"\nDS CLI installed to: {launcher_path}\n"
            "PATH already configured — run `ds` from anywhere."
        )
    else:
        path_instructions = (
            f"\nDS CLI installed to: {launcher_path}\n"
            f"PATH auto-config failed ({path_result.get('error', 'unknown')}). "
            "Add ~/.dream-studio/bin to PATH manually."
        )

    return {
        "launcher_path": str(launcher_path),
        "bin_dir": str(bin_dir),
        "is_windows": is_windows,
        "path_result": path_result,
        "path_instructions": path_instructions,
    }


def _first_run_guide(*, ds_home: Path) -> str | None:
    """Return first-run guide text if no active projects exist in DB, else None."""
    sqlite_path = ds_home / "state" / "studio.db"
    if not sqlite_path.exists():
        return _FIRST_RUN_GUIDE_TEXT
    try:
        _sq3 = __import__("sqlite3")
        with _sq3.connect(str(sqlite_path)) as conn:
            rows = conn.execute(
                "SELECT 1 FROM business_projects WHERE status = 'active' LIMIT 1"
            ).fetchall()
        if rows:
            return None
    except Exception:
        pass
    return _FIRST_RUN_GUIDE_TEXT


_FIRST_RUN_GUIDE_TEXT = """
Dream Studio is installed.
No active project detected.

Step 0 — Personalize your environment
Fill in your identity in config.json:
  ~/.dream-studio/config.json
Set: director_name, domain, primary_use
Example:
  {
    "director_name": "Your Name",
    "domain": "software development",
    "primary_use": "client projects and internal tools"
  }
These fields personalize all project intelligence
outputs, coaching, and daily standup briefings.
Without them all responses are generic.

Get started in 4 steps:
  1. Register your project:
     ds project register --name "Your Project"
  2. Set it active:
     ds project set-active <project_id>
  3. Scope it (guided conversation):
     ds skill invoke ds-project:scope
  4. Start your first work order:
     ds project next <project_id>
     ds work-order start <work_order_id>

Run `ds doctor` at any time to check health."""


def _get_ds_version() -> str:
    try:
        from core.config.sqlite_bootstrap import latest_migration_version

        return f"migration-{latest_migration_version()}"
    except Exception:
        return "unknown"
