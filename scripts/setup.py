"""
scripts/setup.py — dream-studio first-run setup

Usage:
    py scripts/setup.py          (from repo root)
    python scripts/setup.py

Requirements: Python 3.11+, no third-party dependencies.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import venv
from pathlib import Path
from typing import NamedTuple

# Force UTF-8 output on all platforms so Unicode markers render correctly.
# On Windows the default console codec is cp1252 which lacks checkmark glyphs.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = REPO_ROOT / ".venv"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"
SETTINGS_JSON = Path.home() / ".claude" / "settings.json"


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

class StepResult(NamedTuple):
    name: str
    passed: bool
    detail: str = ""


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------

def step_python_version() -> StepResult:
    """FR-S01: Require Python 3.11+."""
    name = "Python version check"
    v = sys.version_info
    if v >= (3, 11):
        return StepResult(name, True, f"Python {v.major}.{v.minor}.{v.micro}")
    msg = (
        f"ERROR: Python 3.11+ required. You have Python {v.major}.{v.minor}. "
        "Download from https://python.org/downloads/"
    )
    print(msg)
    return StepResult(name, False, f"Python {v.major}.{v.minor} is too old")


def _venv_pip() -> Path:
    """Return the pip executable inside the venv, cross-platform."""
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


def step_venv_and_deps() -> StepResult:
    """FR-S02: Create .venv if absent, then install requirements."""
    name = "venv creation + dep install"
    try:
        if not VENV_DIR.exists():
            venv.create(str(VENV_DIR), with_pip=True)

        pip = _venv_pip()

        # If pip is missing (e.g. partial venv), repair it via ensurepip.
        if not pip.exists():
            venv_python: Path
            if platform.system() == "Windows":
                venv_python = VENV_DIR / "Scripts" / "python.exe"
            else:
                venv_python = VENV_DIR / "bin" / "python"

            if not venv_python.exists():
                return StepResult(name, False, f"venv Python not found at {venv_python}")

            repair = subprocess.run(
                [str(venv_python), "-m", "ensurepip", "--upgrade"],
                capture_output=True,
                text=True,
            )
            if repair.returncode != 0 or not pip.exists():
                return StepResult(
                    name,
                    False,
                    "pip not found and ensurepip failed: "
                    + (repair.stderr or repair.stdout or "").strip(),
                )

        if not REQUIREMENTS.exists():
            return StepResult(name, False, f"requirements.txt not found at {REQUIREMENTS}")

        result = subprocess.run(
            [str(pip), "install", "-r", str(REQUIREMENTS)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            last_line = detail[-1] if detail else "unknown error"
            return StepResult(name, False, last_line)

        return StepResult(name, True)
    except Exception as exc:  # noqa: BLE001
        return StepResult(name, False, str(exc))


def _collect_commands(hook_list: list[dict]) -> set[str]:
    """Return all command strings from a hooks event list."""
    commands: set[str] = set()
    for group in hook_list:
        for hook in group.get("hooks", []):
            cmd = hook.get("command")
            if cmd:
                commands.add(cmd)
    return commands


def step_settings_merge() -> StepResult:
    """FR-S03: Non-destructively merge hooks/hooks.json into ~/.claude/settings.json."""
    name = "settings.json hooks merge"
    try:
        # Load source hooks
        if not HOOKS_JSON.exists():
            return StepResult(name, False, f"hooks.json not found at {HOOKS_JSON}")

        with HOOKS_JSON.open(encoding="utf-8") as fh:
            source_data: dict = json.load(fh)
        source_hooks: dict[str, list] = source_data.get("hooks", {})

        # Load or initialise settings.json
        SETTINGS_JSON.parent.mkdir(parents=True, exist_ok=True)
        if SETTINGS_JSON.exists():
            with SETTINGS_JSON.open(encoding="utf-8") as fh:
                settings: dict = json.load(fh)
        else:
            settings = {}

        if "hooks" not in settings:
            settings["hooks"] = {}

        added = 0
        for event_type, source_groups in source_hooks.items():
            existing_groups: list[dict] = settings["hooks"].setdefault(event_type, [])
            existing_commands = _collect_commands(existing_groups)

            for source_group in source_groups:
                # Determine which hook entries in this group are new
                new_hooks = [
                    hook
                    for hook in source_group.get("hooks", [])
                    if hook.get("command") not in existing_commands
                ]
                if not new_hooks:
                    continue

                # Build a group dict that preserves optional "matcher" key
                new_group: dict = {}
                if "matcher" in source_group:
                    new_group["matcher"] = source_group["matcher"]
                new_group["hooks"] = new_hooks

                existing_groups.append(new_group)
                # Update the known-commands set so subsequent groups in the
                # same event don't re-add the same command.
                for hook in new_hooks:
                    existing_commands.add(hook.get("command", ""))
                added += len(new_hooks)

        with SETTINGS_JSON.open("w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
            fh.write("\n")

        return StepResult(name, True, f"{added} new hook entries merged")
    except Exception as exc:  # noqa: BLE001
        return StepResult(name, False, str(exc))


def _repo_slug() -> str:
    """
    Convert the repo's absolute path to a Claude project slug.

    Rules:
      - Remove drive colon (C: → C)
      - Replace all path separators (/ and \\) with -
      - Example: C:\\Users\\foo\\builds\\dream-studio → C--Users-foo-builds-dream-studio
    """
    raw = str(REPO_ROOT)
    # Remove drive colon (Windows: "C:" → "C")
    if len(raw) >= 2 and raw[1] == ":":
        raw = raw[0] + raw[2:]
    # Normalise to forward slashes then split/join with -
    raw = raw.replace("\\", "/")
    parts = [p for p in raw.split("/") if p]
    slug = "-".join(parts)
    # Replace spaces (e.g. "Dannis Seay" in home path) with hyphens
    slug = slug.replace(" ", "-")
    return slug


def step_memory_init() -> StepResult:
    """FR-S04: Create ~/.claude/projects/<slug>/memory/ and seed MEMORY.md."""
    name = "Memory dir init"
    try:
        slug = _repo_slug()
        memory_dir = Path.home() / ".claude" / "projects" / slug / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        memory_file = memory_dir / "MEMORY.md"
        if not memory_file.exists():
            memory_file.write_text(
                "# Memory Index\n\n*No memories yet. Run a session to populate.*\n",
                encoding="utf-8",
            )
            return StepResult(name, True, f"Created {memory_file}")

        return StepResult(name, True, f"Already exists: {memory_file}")
    except Exception as exc:  # noqa: BLE001
        return StepResult(name, False, str(exc))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    print("[dream-studio] First-run setup")
    print()

    steps = [
        step_python_version,
        step_venv_and_deps,
        step_settings_merge,
        step_memory_init,
    ]

    results: list[StepResult] = []
    abort = False

    for fn in steps:
        result = fn()
        results.append(result)
        # Python version failure is fatal — remaining steps depend on 3.11+.
        if not result.passed and fn is step_python_version:
            abort = True
            break

    print("Setup checklist:")
    for r in results:
        if r.passed:
            marker = "  ✓"
            suffix = f" ({r.detail})" if r.detail else ""
            print(f"{marker} {r.name}{suffix}")
        else:
            print(f"  ✗ {r.name} — {r.detail}")

    if abort:
        # Print remaining steps as skipped so the user sees the full picture.
        remaining = steps[len(results):]
        for fn in remaining:
            # Produce a placeholder name from the function's docstring first line
            doc = (fn.__doc__ or fn.__name__).strip().splitlines()[0]
            # Strip leading "FR-Sxx: " prefix if present
            label = doc.split(": ", 1)[-1] if ": " in doc else doc
            print(f"  - {label} (skipped)")

    all_passed = all(r.passed for r in results) and not abort
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
