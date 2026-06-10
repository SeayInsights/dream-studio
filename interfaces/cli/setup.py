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
# File-write audit (T1 — WO-SETUP2)
# ---------------------------------------------------------------------------
# Every file write in this script is listed below. Anything not listed is
# read-only. This comment is the canonical record; keep it current.
#
# step_venv_and_deps()        → <repo>/.venv/          (created if absent; pip-managed)
# step_settings_merge()       → ~/.claude/settings.json (non-destructive merge: existing
#                               non-hook keys preserved; existing hook commands never
#                               removed; only new DS groups appended)
#                             → does NOT touch ~/.claude/CLAUDE.md or any other user file
# step_memory_init()          → ~/.claude/projects/<slug>/memory/MEMORY.md
#                               (created only if the file does not already exist — no overwrite)
# step_analytics_bootstrap()  → ~/.dream-studio/state/studio.db (delegated to studio_db)
# step_first_run_marker()     → ~/.dream-studio/state/first-run-pending (overwrite: safe,
#                               DS-owned marker file, not user data)
# step_sync_hook_projection() → <repo>/.claude/hooks/runtime/hooks/{quality,domains,core,meta}/
#                               (gitignored DS projection; shutil.copy2 per .py file)
#                             → <repo>/.claude/hooks/.plugin-root (overwrite: DS-owned)
# step_local_adapter_excludes()→ <repo>/.git/info/exclude (appends patterns only;
#                               existing lines preserved)
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

                # Build a group dict preserving optional "matcher" and DS ownership marker.
                new_group: dict = {}
                if "matcher" in source_group:
                    new_group["matcher"] = source_group["matcher"]
                if source_group.get("dream_studio_managed"):
                    new_group["dream_studio_managed"] = True
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


def step_sync_hook_projection() -> StepResult:
    """FR-RT2: Copy runtime/hooks/ subdirs into .claude/hooks/runtime/hooks/ and fix .plugin-root."""
    name = "Hook projection sync"
    try:
        import shutil

        src_base = REPO_ROOT / "runtime" / "hooks"
        dst_base = REPO_ROOT / ".claude" / "hooks" / "runtime" / "hooks"

        if not src_base.exists():
            return StepResult(name, False, f"source not found: {src_base}")

        copied = 0
        for sub in ("quality", "domains", "core", "meta"):
            src_dir = src_base / sub
            dst_dir = dst_base / sub
            if not src_dir.exists():
                continue
            dst_dir.mkdir(parents=True, exist_ok=True)
            for src_file in src_dir.rglob("*.py"):
                if "__pycache__" in src_file.parts:
                    continue
                dst_file = dst_dir / src_file.relative_to(src_dir)
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied += 1

        plugin_root = REPO_ROOT / ".claude" / "hooks" / ".plugin-root"
        plugin_root.write_text(str(REPO_ROOT / ".claude" / "hooks"), encoding="utf-8")

        return StepResult(name, True, f"{copied} files synced, .plugin-root updated")
    except Exception as exc:  # noqa: BLE001
        return StepResult(name, False, str(exc))


def step_uninstall() -> int:
    """Remove Dream Studio hook entries and projection files. Leaves user hooks untouched."""
    import shutil

    print("[dream-studio] Uninstall")
    print()

    removed_hooks: list[str] = []
    kept_hooks: list[str] = []
    removed_files: list[str] = []
    errors: list[str] = []

    # 1 — Remove DS hook groups from ~/.claude/settings.json
    if SETTINGS_JSON.exists():
        try:
            with SETTINGS_JSON.open(encoding="utf-8") as fh:
                settings: dict = json.load(fh)
            hooks_section: dict = settings.get("hooks", {})
            changed = False
            for event_type, groups in list(hooks_section.items()):
                keep = []
                for group in groups:
                    if group.get("dream_studio_managed"):
                        for hook in group.get("hooks", []):
                            removed_hooks.append(f"{event_type}: {hook.get('command', '')[:60]}…")
                        changed = True
                    else:
                        for hook in group.get("hooks", []):
                            kept_hooks.append(f"{event_type}: {hook.get('command', '')[:60]}…")
                        keep.append(group)
                hooks_section[event_type] = keep
            if changed:
                with SETTINGS_JSON.open("w", encoding="utf-8") as fh:
                    json.dump(settings, fh, indent=2)
                    fh.write("\n")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"settings.json: {exc}")
    else:
        print("  settings.json not found — skipping hook removal")

    # 2 — Remove .claude/hooks/ DS projection subdirs (gitignored, DS-owned)
    projection_root = REPO_ROOT / ".claude" / "hooks" / "runtime" / "hooks"
    for sub in ("quality", "domains", "core"):
        sub_dir = projection_root / sub
        if sub_dir.exists():
            try:
                shutil.rmtree(sub_dir)
                removed_files.append(str(sub_dir))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{sub_dir}: {exc}")

    # 3 — Remove .plugin-root
    plugin_root = REPO_ROOT / ".claude" / "hooks" / ".plugin-root"
    if plugin_root.exists():
        try:
            plugin_root.unlink()
            removed_files.append(str(plugin_root))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{plugin_root}: {exc}")

    # Report
    print(f"  Removed {len(removed_hooks)} DS hook entries:")
    for h in removed_hooks:
        print(f"    - {h}")
    print(f"  Kept {len(kept_hooks)} non-DS hook entries intact")
    print(f"  Removed {len(removed_files)} projection files/dirs")
    for f in removed_files:
        print(f"    - {f}")
    if errors:
        print("  Errors:")
        for e in errors:
            print(f"    ✗ {e}")
        return 1

    print()
    print("Uninstall complete. Re-run setup.py to reinstall.")
    return 0


def test_coexistence() -> int:
    """T4: Verify pre-existing user hooks survive install and are not removed on uninstall."""
    import tempfile, copy

    print("[dream-studio] Coexistence test")
    failures: list[str] = []

    # Mock settings.json with a pre-existing hook from another tool
    pre_existing: dict = {
        "model": "claude-opus-4-5",
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "echo 'user-hook-from-other-tool'"}]}
            ]
        },
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_settings = Path(tmpdir) / "settings.json"
        tmp_settings.write_text(json.dumps(pre_existing, indent=2), encoding="utf-8")

        # Temporarily redirect SETTINGS_JSON
        import interfaces.cli.setup as _self

        orig = _self.SETTINGS_JSON
        _self.SETTINGS_JSON = tmp_settings
        try:
            # --- Install ---
            result = step_settings_merge()
            if not result.passed:
                failures.append(f"install failed: {result.detail}")
            else:
                with tmp_settings.open(encoding="utf-8") as fh:
                    after_install: dict = json.load(fh)

                # Pre-existing hook must still be present
                ups = after_install.get("hooks", {}).get("UserPromptSubmit", [])
                user_cmds = [h.get("command") for g in ups for h in g.get("hooks", [])]
                if "echo 'user-hook-from-other-tool'" not in user_cmds:
                    failures.append("install: pre-existing user hook was removed")

                # model key must be preserved
                if after_install.get("model") != "claude-opus-4-5":
                    failures.append("install: non-hook key 'model' was lost")

                # DS hooks must have been added with marker
                ds_groups = [g for g in ups if g.get("dream_studio_managed")]
                if not ds_groups:
                    failures.append("install: no dream_studio_managed groups written")

                # --- Uninstall (settings only — skip projection file removal in test) ---
                import interfaces.cli.setup as _self2

                orig_repo = _self2.REPO_ROOT
                # Point REPO_ROOT at a temp dir so projection removal is a no-op
                _self2.REPO_ROOT = Path(tmpdir)
                (Path(tmpdir) / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
                try:
                    uninstall_rc = step_uninstall()
                finally:
                    _self2.REPO_ROOT = orig_repo
                if uninstall_rc != 0:
                    failures.append(f"uninstall returned {uninstall_rc}")
                else:
                    with tmp_settings.open(encoding="utf-8") as fh:
                        after_uninstall: dict = json.load(fh)

                    ups2 = after_uninstall.get("hooks", {}).get("UserPromptSubmit", [])
                    remaining_cmds = [h.get("command") for g in ups2 for h in g.get("hooks", [])]

                    if "echo 'user-hook-from-other-tool'" not in remaining_cmds:
                        failures.append("uninstall: pre-existing user hook was removed")

                    ds_remaining = [g for g in ups2 if g.get("dream_studio_managed")]
                    if ds_remaining:
                        failures.append("uninstall: DS hook groups still present after uninstall")

                    if after_uninstall.get("model") != "claude-opus-4-5":
                        failures.append("uninstall: non-hook key 'model' was lost")
        finally:
            _self.SETTINGS_JSON = orig

    if failures:
        print("  FAIL:")
        for f in failures:
            print(f"    ✗ {f}")
        return 1

    print("  ✓ pre-existing hooks preserved after install")
    print("  ✓ non-hook settings preserved after install")
    print("  ✓ DS hooks written with dream_studio_managed marker")
    print("  ✓ DS hooks removed on uninstall")
    print("  ✓ pre-existing hooks intact after uninstall")
    print("  ✓ non-hook settings preserved after uninstall")
    return 0


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


def _local_adapter_exclude_report() -> dict:
    """Return local adapter scratch exclude status without writing files."""
    try:
        from core.release.adapter_workspace_hygiene import required_local_exclude_patterns

        exclude_path = REPO_ROOT / ".git" / "info" / "exclude"
        existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
        configured = {
            line.strip()
            for line in existing.splitlines()
            if line.strip() and not line.startswith("#")
        }
        patterns = list(required_local_exclude_patterns())
        return {
            "available": True,
            "exclude_path": str(exclude_path),
            "patterns": patterns,
            "missing_patterns": [pattern for pattern in patterns if pattern not in configured],
            "local_only": True,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "error": str(exc),
            "local_only": True,
        }


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


def _projection_completeness_report() -> dict:
    """Return DS hook projection health without writing anything."""
    projection_root = REPO_ROOT / ".claude" / "hooks" / "runtime" / "hooks"
    plugin_root_path = REPO_ROOT / ".claude" / "hooks" / ".plugin-root"
    expected_subdirs = ("meta", "quality", "domains", "core")

    present = [s for s in expected_subdirs if (projection_root / s).is_dir()]
    missing = [s for s in expected_subdirs if s not in present]

    plugin_root_ok = False
    plugin_root_value = ""
    expected_plugin_root = str(REPO_ROOT / ".claude" / "hooks")
    if plugin_root_path.exists():
        plugin_root_value = plugin_root_path.read_text(encoding="utf-8").strip()
        plugin_root_ok = plugin_root_value == expected_plugin_root

    # Check settings.json for DS hook presence
    ds_hooks_present = False
    if SETTINGS_JSON.exists():
        try:
            with SETTINGS_JSON.open(encoding="utf-8") as fh:
                settings = json.load(fh)
            for groups in settings.get("hooks", {}).values():
                if any(g.get("dream_studio_managed") for g in groups):
                    ds_hooks_present = True
                    break
        except Exception:
            pass

    return {
        "present_subdirs": present,
        "missing_subdirs": missing,
        "plugin_root_ok": plugin_root_ok,
        "plugin_root_value": plugin_root_value,
        "plugin_root_expected": expected_plugin_root,
        "ds_hooks_present": ds_hooks_present,
        "all_ok": not missing and plugin_root_ok and ds_hooks_present,
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
    adapter_excludes = _local_adapter_exclude_report()
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
                "adapter_workspace_hygiene": adapter_excludes,
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

    adapter_excludes = _local_adapter_exclude_report()
    if adapter_excludes["available"]:
        missing = adapter_excludes["missing_patterns"]
        marker = "  [ok]" if not missing else "  [warn]"
        detail = (
            "configured" if not missing else "missing local-only patterns: " + ", ".join(missing)
        )
        print(f"{marker} Adapter workspace local excludes - {detail}")
    else:
        print(
            "  [warn] Adapter workspace local excludes unavailable - "
            f"{adapter_excludes['error']}"
        )

    schema_blocked = _print_schema_compatibility()
    if schema_blocked:
        print(
            "    setup --check policy: advisory exit 0; treat blocked_newer_than_code "
            "as a readiness blocker for setup --apply, dashboard bootstrap, and migration checks."
        )

    proj = _projection_completeness_report()
    ds_marker = "  ✓" if proj["ds_hooks_present"] else "  ✗"
    print(f"{ds_marker} DS hooks in settings.json (dream_studio_managed)")
    subdirs_ok = not proj["missing_subdirs"]
    subdirs_marker = "  ✓" if subdirs_ok else "  ✗"
    subdirs_detail = (
        "meta/quality/domains/core all present"
        if subdirs_ok
        else f"missing: {', '.join(proj['missing_subdirs'])}"
    )
    print(f"{subdirs_marker} .claude/hooks/ projection — {subdirs_detail}")
    pr_marker = "  ✓" if proj["plugin_root_ok"] else "  ✗"
    pr_detail = (
        proj["plugin_root_value"]
        if proj["plugin_root_ok"]
        else f"got '{proj['plugin_root_value']}' expected '{proj['plugin_root_expected']}'"
    )
    print(f"{pr_marker} .plugin-root — {pr_detail}")

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
    group.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove DS hook entries (dream_studio_managed=true) and projection files",
    )
    group.add_argument(
        "--test-coexistence",
        action="store_true",
        dest="test_coexistence",
        help="Run install/uninstall coexistence test against a mock settings.json",
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

    if args.uninstall:
        return step_uninstall()

    if args.test_coexistence:
        return test_coexistence()

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
        step_local_adapter_excludes,
        step_venv_and_deps,
        step_settings_merge,
        step_memory_init,
        step_analytics_bootstrap,
        step_first_run_marker,
        step_sync_hook_projection,
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
