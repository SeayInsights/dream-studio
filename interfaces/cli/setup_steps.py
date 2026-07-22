"""dream-studio setup — venv/deps/memory/analytics/marker/excludes steps.

Split from interfaces/cli/setup.py (WO-GF-CLI-split). Hook-related steps
(settings merge, hook projection sync, uninstall, coexistence test) live in
setup_hooks.py; diagnostics-only reporting lives in setup_diagnostics.py.
"""

from __future__ import annotations

import platform
import subprocess
import sys
import venv
from pathlib import Path

from interfaces.cli.setup_shared import REPO_ROOT, REQUIREMENTS, StepResult, VENV_DIR

# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def step_python_version(*, emit: bool = True) -> StepResult:
    """FR-S01: Require Python 3.11+."""
    name = "Python version check"
    v = sys.version_info
    if v >= (3, 11):
        return StepResult(name, True, f"Python {v.major}.{v.minor}.{v.micro}")
    msg = (
        f"ERROR: Python 3.11+ required. You have Python {v.major}.{v.minor}. "
        "Download from https://python.org/downloads/"
    )
    if emit:
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


def _repo_slug() -> str:
    """
    Convert the repo's absolute path to a Claude project slug.

    Rules:
      - Remove drive colon (C: → C)
      - Replace all path separators (/ and \\) with -
      - Example: C:\\Users\\Example\\builds\\dream-studio -> C--Users-Example-builds-dream-studio
    """
    raw = str(REPO_ROOT)
    # Remove drive colon (Windows: "C:" → "C")
    if len(raw) >= 2 and raw[1] == ":":
        raw = raw[0] + raw[2:]
    # Normalise to forward slashes then split/join with -
    raw = raw.replace("\\", "/")
    parts = [p for p in raw.split("/") if p]
    slug = "-".join(parts)
    # Replace spaces in home paths with hyphens.
    slug = slug.replace(" ", "-")
    return slug


def step_first_run_marker() -> StepResult:
    """FR-S06: Write first-run-pending marker so on-first-run hook triggers onboarding."""
    name = "First-run marker"
    try:
        state_dir = Path.home() / ".dream-studio" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        marker = state_dir / "first-run-pending"
        marker.write_text("pending", encoding="utf-8")
        return StepResult(name, True, str(marker))
    except Exception as exc:  # noqa: BLE001
        return StepResult(name, False, str(exc))


def step_analytics_bootstrap() -> StepResult:
    """FR-S05: Initialize analytics database and harvest existing data."""
    name = "Analytics DB bootstrap"
    try:
        import importlib

        hooks_dir = REPO_ROOT / "hooks"
        sys.path.insert(0, str(hooks_dir))
        sys.path.insert(0, str(REPO_ROOT / "scripts"))

        lib_paths = importlib.import_module("core.config.paths")
        studio_db = importlib.import_module("core.event_store.studio_db")

        # Create DB + run migrations (idempotent)
        conn = studio_db._connect()
        version = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] or 0
        conn.close()

        # Harvest existing pulse data
        harvested = 0
        try:
            backfill_pulse = importlib.import_module("ds_analytics.backfill_pulse")
            harvested += backfill_pulse.backfill()
        except Exception:
            pass

        # Harvest token log if present (raw_sessions backfill — raw_token_usage
        # was dropped in migration 138)
        token_log = lib_paths.meta_dir() / "token-log.md"
        if token_log.is_file():
            try:
                bts = importlib.import_module("backfill_token_sessions")
                result = bts.backfill_sessions()
                harvested += result.get("inserted", 0)
            except Exception:
                pass

        detail = f"schema v{version}"
        if harvested:
            detail += f", {harvested} rows harvested"

        return StepResult(name, True, detail)
    except Exception as exc:  # noqa: BLE001
        return StepResult(name, False, str(exc))


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


def step_local_adapter_excludes() -> StepResult:
    """Configure checkout-local adapter scratch/worktree excludes."""
    name = "Adapter workspace local excludes"
    try:
        from core.release.adapter_workspace_hygiene import ensure_local_git_excludes

        result = ensure_local_git_excludes(REPO_ROOT)
        added = result["added"]
        if added:
            return StepResult(name, True, f"added {', '.join(added)}")
        return StepResult(name, True, "already configured")
    except Exception as exc:  # noqa: BLE001
        return StepResult(name, False, str(exc))
