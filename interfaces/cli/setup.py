"""
dream-studio setup — first-run setup, doctor check, and update.

Usage:
    py interfaces/cli/setup.py               # full setup (writes files)
    py interfaces/cli/setup.py --check       # read-only doctor report
    py interfaces/cli/setup.py --help        # print help only

Re-run after ``git pull`` to sync settings and pick up any new hooks.
Requirements: Python 3.11+, no third-party dependencies.
"""

from __future__ import annotations

import argparse
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

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
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
    # Replace spaces in home paths with hyphens.
    slug = slug.replace(" ", "-")
    return slug


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

        # Harvest token log if present
        token_log = lib_paths.meta_dir() / "token-log.md"
        if token_log.is_file():
            try:
                bts = importlib.import_module("backfill_token_sessions")
                result = bts.backfill_token_usage()
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


def _schema_compatibility_report() -> dict:
    """Return runtime DB/code compatibility details without creating or migrating the DB."""
    try:
        from interfaces.cli.runtime_preflight import (
            format_schema_compatibility,
            inspect_schema_compatibility,
            schema_compatibility_is_blocking,
        )

        result = inspect_schema_compatibility(repo_root=REPO_ROOT)
        return {
            "available": True,
            "result": result,
            "formatted": format_schema_compatibility(result),
            "blocked": schema_compatibility_is_blocking(result),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "result": {},
            "formatted": "",
            "blocked": False,
            "error": str(exc),
        }


def _print_schema_compatibility() -> bool:
    """Report runtime DB/code compatibility without creating or migrating the DB."""
    report = _schema_compatibility_report()
    if not report["available"]:
        print(f"  [warn] Runtime DB schema compatibility unavailable: {report['error']}")
        return False

    result = report["result"]
    label = "ok" if result.get("severity") == "info" else result.get("severity", "warn")
    print(f"  [{label}] Runtime DB schema compatibility")
    for line in report["formatted"].splitlines():
        print(f"    {line}")
    return bool(report["blocked"])


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _check_only_json() -> int:
    """Read-only doctor report for operator/dashboard automation."""
    if not HOOKS_JSON.exists():
        print(
            json.dumps(
                {
                    "mode": "check",
                    "read_only": True,
                    "repo_root": str(REPO_ROOT),
                    "ready_for_apply": False,
                    "error": f"hooks.json not found at {HOOKS_JSON}",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    results = [step_python_version(emit=False)]
    schema_report = _schema_compatibility_report()
    schema_blocked = bool(schema_report["blocked"])
    files = [
        {"label": label, "path": str(path), "exists": path.exists()}
        for label, path in [
            ("requirements.txt", REQUIREMENTS),
            ("hooks.json", HOOKS_JSON),
            (".venv", VENV_DIR),
            ("settings.json", SETTINGS_JSON),
        ]
    ]
    print(
        json.dumps(
            {
                "mode": "check",
                "read_only": True,
                "repo_root": str(REPO_ROOT),
                "ready_for_apply": all(r.passed for r in results) and not schema_blocked,
                "check_policy": {
                    "blocked_newer_than_code": "advisory_exit_0_for_check",
                },
                "steps": [
                    {"name": r.name, "passed": r.passed, "detail": r.detail} for r in results
                ],
                "files": files,
                "schema_compatibility": schema_report,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _check_only() -> int:
    """Read-only doctor: report prerequisites without writing anything."""
    print("[dream-studio] Doctor check (read-only)")
    print()

    checks = [
        ("Python version", step_python_version),
    ]
    # Validate repo root before anything else
    if not HOOKS_JSON.exists():
        print(f"  ✗ Repo root — hooks.json not found at {HOOKS_JSON}")
        print("    Run from the repo root: py interfaces/cli/setup.py --check")
        return 1

    results: list[StepResult] = [fn() for _, fn in checks]

    # Report file existence (read-only)
    for label, path in [
        ("requirements.txt", REQUIREMENTS),
        ("hooks.json", HOOKS_JSON),
        (".venv", VENV_DIR),
        ("settings.json", SETTINGS_JSON),
    ]:
        exists = path.exists()
        marker = "  ✓" if exists else "  ✗"
        print(f"{marker} {label} {'exists' if exists else 'missing'} — {path}")

    for r in results:
        marker = "  ✓" if r.passed else "  ✗"
        suffix = f" ({r.detail})" if r.detail else ""
        print(f"{marker} {r.name}{suffix}")

    schema_blocked = _print_schema_compatibility()
    if schema_blocked:
        print(
            "    setup --check policy: advisory exit 0; treat blocked_newer_than_code "
            "as a readiness blocker for setup --apply, dashboard bootstrap, and migration checks."
        )

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="setup.py",
        description="dream-studio first-run setup and doctor check.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        action="store_true",
        help="Read-only doctor report (creates no files)",
    )
    group.add_argument(
        "--apply",
        action="store_true",
        help="Full setup: create venv, merge hooks, seed memory (default if no flag)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="With --check, emit a machine-readable read-only readiness report",
    )
    args = parser.parse_args(argv)

    if args.json and not args.check:
        parser.error("--json is only supported with --check")

    if args.check:
        if args.json:
            return _check_only_json()
        return _check_only()

    # Default behavior (no flag or --apply): full setup
    # Validate repo root early — fail before any filesystem mutation
    if not HOOKS_JSON.exists():
        print(f"ERROR: hooks.json not found at {HOOKS_JSON}", file=sys.stderr)
        print("Run from the repo root directory.", file=sys.stderr)
        return 1

    print("[dream-studio] First-run setup")
    print()

    steps = [
        step_python_version,
        step_venv_and_deps,
        step_settings_merge,
        step_memory_init,
        step_analytics_bootstrap,
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
        remaining = steps[len(results) :]
        for fn in remaining:
            doc = (fn.__doc__ or fn.__name__).strip().splitlines()[0]
            label = doc.split(": ", 1)[-1] if ": " in doc else doc
            print(f"  - {label} (skipped)")

    all_passed = all(r.passed for r in results) and not abort
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
