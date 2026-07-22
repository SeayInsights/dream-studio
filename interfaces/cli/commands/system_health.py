"""ds system command group — health/status/doctor/validate/migrate subcommands.

Split from interfaces/cli/commands/system.py (WO-GF-CLI-split). The facade at
interfaces/cli/commands/system.py re-exports this module's public+private
surface; interfaces/cli/commands/system_dispatch.py composes register_health()/
dispatch_health() together with the other three group siblings.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from interfaces.cli.cli_utils import _print, _with_conn

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------

#: Commands handled by this group.
HEALTH_COMMANDS = frozenset(
    {
        "status",
        "version",
        "doctor",
        "repair",
        "update",
        "validate",
        "migrate",
        "modules",
        "adapters",
        "router",
        "platform-hardening",
    }
)


def register_health(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach health/status/doctor/validate/migrate subparsers to *subcommands*."""

    subcommands.add_parser("status", help="Show installed runtime status")
    subcommands.add_parser("version", help="Show Dream Studio source/runtime version")

    _doctor_cmd = subcommands.add_parser(
        "doctor",
        help="Verify Claude Code integration health (skills, agents, hooks, routing)",
        description=(
            "Verify Claude Code integration health: dispatcher hooks wired, skills\n"
            "installed and current, agents deployed, routing triggers covered, version\n"
            "current. Use this after `ds integrate install` or before starting a session.\n"
            "For DB-level health (schema version, migrations), use `ds validate`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _doctor_cmd.add_argument("--fix", action="store_true", help="Attempt to fix failing checks")
    _doctor_cmd.add_argument(
        "mode",
        nargs="?",
        default=None,
        help=(
            "Optional mode.  Supported values:\n"
            "  dashboard-truth  Run live-authority invariant checks against the SQLite DB."
        ),
    )

    subcommands.add_parser("repair", help="Plan repair actions without mutating state")

    _update_cmd = subcommands.add_parser("update", help="Update Dream Studio integration pack")
    _update_cmd.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Show what would change without installing",
    )

    subcommands.add_parser(
        "validate",
        help="Verify DB health (schema version, migrations, module profiles)",
        description=(
            "Verify DB health: schema version, migration completeness, module profile\n"
            "validity. Use this after migrations or DB-related changes. For Claude Code\n"
            "integration health (skills, agents, hooks, routing), use `ds doctor`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subcommands.add_parser("adapters", help="Show adapter status")
    subcommands.add_parser("modules", help="Show module profile status")
    subcommands.add_parser("router", help="Show adapter router status")
    subcommands.add_parser("platform-hardening", help="Show platform hardening status")

    migrate_cmd = subcommands.add_parser(
        "migrate", help="Manage migration activation state on the live authority DB"
    )
    migrate_sub = migrate_cmd.add_subparsers(dest="migrate_subcommand", required=True)
    migrate_sub.add_parser("status", help="Show merged-but-not-activated migrations")
    migrate_activate_cmd = migrate_sub.add_parser(
        "activate",
        help="Apply pending-activation migrations (operator-invoked; creates backup first)",
    )
    migrate_activate_cmd.add_argument(
        "--db-path",
        default=None,
        dest="db_path",
        help="Override live DB path (default: ~/.dream-studio/state/studio.db)",
    )
    migrate_activate_cmd.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Skip interactive confirmation prompt and apply immediately",
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch_health(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Route a health/status/doctor/validate/migrate command to its implementation."""
    from core.installed_runtime import adapter_router_status
    from core.module_profiles import module_profiles
    from core.shared_intelligence.platform_hardening import platform_hardening_summary

    if args.command == "status":
        from core.health.status import get_runtime_status

        return _print(
            get_runtime_status(source_root=source_root, dream_studio_home=dream_studio_home)
        )

    if args.command == "version":
        return _print(_version_status(source_root=source_root, dream_studio_home=dream_studio_home))

    if args.command == "doctor":
        _doctor_mode = getattr(args, "mode", None)
        if _doctor_mode == "dashboard-truth":
            from core.gates.dashboard_truth import run_dashboard_truth
            from interfaces.cli.ds import resolve_installed_runtime_paths

            _dt_paths = resolve_installed_runtime_paths(
                source_root=source_root,
                dream_studio_home=dream_studio_home,
            )
            _dt_result = run_dashboard_truth(_dt_paths.sqlite_path)
            for _inv in _dt_result["results"]:
                _status = "PASS" if _inv["passed"] else "FAIL"
                _err = f" — {_inv['error']}" if _inv["error"] else ""
                print(f"[dashboard-truth] {_status}: {_inv['name']}{_err}")
            if not _dt_result["ok"]:
                print("[dashboard-truth] OVERALL: FAIL — one or more invariants failed")
                return 1
            print("[dashboard-truth] OVERALL: PASS")
            return 0
        return _print(
            _doctor_status(
                source_root=source_root,
                dream_studio_home=dream_studio_home,
                fix=getattr(args, "fix", False),
            )
        )

    if args.command == "update":
        return _update_command(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            dry_run=getattr(args, "dry_run", False),
        )

    if args.command == "repair":
        return _print(_repair_plan(source_root=source_root, dream_studio_home=dream_studio_home))

    if args.command == "validate":
        return _print(
            _validate_status(source_root=source_root, dream_studio_home=dream_studio_home)
        )

    if args.command == "migrate":
        return _migrate_command(args)

    if args.command == "modules":
        return _print(module_profiles())

    if args.command in {"adapters", "router"}:
        return _with_conn(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            callback=lambda conn: adapter_router_status(
                conn,
                source_root=source_root,
                dream_studio_home=dream_studio_home,
            ),
        )

    if args.command == "platform-hardening":
        return _with_conn(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            callback=platform_hardening_summary,
        )

    return 1


# ---------------------------------------------------------------------------
# Implementation helpers
# ---------------------------------------------------------------------------


def _version_status(*, source_root: Path, dream_studio_home: Path | None) -> dict[str, Any]:
    from core.health.version import get_version

    return get_version(source_root=source_root, dream_studio_home=dream_studio_home)


def _check_dispatcher_hooks(claude_dir: Path) -> bool:
    """Return True if the DS dispatcher hook is registered for UserPromptSubmit."""
    _DISPATCHER_MARKERS = (
        "hooks\\dispatch\\hooks.py",  # installed path (Windows)
        "hooks/dispatch/hooks.py",  # installed path (Unix)
        "runtime/dispatch/hooks",  # legacy repo-relative path
        "'dispatch'/'hooks.py'",  # legacy pathlib expression
    )
    try:
        settings_path = claude_dir / "settings.json"
        if not settings_path.is_file():
            return False
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        hooks_section = data.get("hooks", {})
        event_entries = hooks_section.get("UserPromptSubmit", [])
        for entry in event_entries:
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if any(m in cmd for m in _DISPATCHER_MARKERS):
                    return True
        return False
    except Exception:
        return False


def _get_expected_skill_ids(source_root: Path) -> list[str]:
    """Derive expected Claude Code skill IDs from canonical/skills/ directory."""
    skills_dir = source_root / "canonical" / "skills"
    if not skills_dir.is_dir():
        return ["ds-bootstrap"]
    ids = [
        (d.name if d.name.startswith("ds-") else f"ds-{d.name}")
        for d in sorted(skills_dir.iterdir())
        if d.is_dir() and (d / "SKILL.md").is_file()
    ]
    return ids or ["ds-bootstrap"]


def _check_skills_installed(claude_dir: Path, source_root: Path | None = None) -> dict[str, Any]:
    """Return skills install status — checks all canonical skill IDs."""
    expected = _get_expected_skill_ids(source_root) if source_root is not None else ["ds-bootstrap"]
    try:
        skills_dir = claude_dir / "skills"
        installed = [sid for sid in expected if (skills_dir / sid / "SKILL.md").is_file()]
        missing = [sid for sid in expected if sid not in installed]
        return {"total_expected": len(expected), "installed": len(installed), "missing": missing}
    except Exception:
        return {"total_expected": len(expected), "installed": 0, "missing": expected}


def _check_agents_installed(claude_dir: Path, source_root: Path) -> dict[str, Any]:
    """Return agents install status — checks canonical/agents/ vs ~/.claude/agents/."""
    try:
        agents_src = source_root / "canonical" / "agents"
        expected = (
            [p.stem for p in agents_src.glob("*.md") if p.name != "README.md"]
            if agents_src.is_dir()
            else []
        )
        agents_dir = claude_dir / "agents"
        installed = [name for name in expected if (agents_dir / f"{name}.md").is_file()]
        missing = [name for name in expected if name not in installed]
        return {"total_expected": len(expected), "installed": len(installed), "missing": missing}
    except Exception:
        return {"total_expected": 0, "installed": 0, "missing": []}


def _check_failed_events(dream_studio_home: Path) -> dict[str, int]:
    """Return count of *.json files in ~/.dream-studio/events/failed/ root only."""
    try:
        failed_dir = dream_studio_home / "events" / "failed"
        if not failed_dir.is_dir():
            return {"count": 0}
        count = sum(1 for p in failed_dir.iterdir() if p.is_file() and p.suffix == ".json")
        return {"count": count}
    except Exception:
        return {"count": 0}


def _check_version_current(source_root: Path, dream_studio_home: Path) -> dict[str, Any]:
    """Compare repo VERSION vs installed-version. Fail-open."""
    try:
        repo_file = source_root / "VERSION"
        installed_file = dream_studio_home / "state" / "installed-version"
        repo_ver = repo_file.read_text(encoding="utf-8").strip() if repo_file.is_file() else None
        installed_ver = (
            installed_file.read_text(encoding="utf-8").strip() if installed_file.is_file() else None
        )
        current = repo_ver is not None and repo_ver == installed_ver
        return {"repo": repo_ver, "installed": installed_ver, "current": current}
    except Exception:
        return {"repo": None, "installed": None, "current": False}


def _doctor_status(
    *, source_root: Path, dream_studio_home: Path | None, fix: bool = False
) -> dict[str, Any]:
    from core.config.platform import ensure_platform_recorded
    from core.health.doctor import run_doctor_checks

    ensure_platform_recorded()
    return run_doctor_checks(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        fix=fix,
    )


def _canonical_hook_drift(source_root: Path, manifest: dict) -> list[str]:
    """Return names of hook meta files whose canonical source has changed since last install.

    The manifest records content_hash = hash(canonical_source) at install time.
    If the canonical source has since been updated (e.g. a bug fix without a version bump),
    the hashes differ and re-projection is required.  Returns an empty list when everything
    matches (no reinstall needed).
    """
    # Index manifest by filename for hook meta files (ignore duplicates — first match wins)
    meta_hashes: dict[str, str] = {}
    for entry in manifest.get("files", []):
        if entry.get("operation") == "skip":
            continue
        p = entry.get("path", "")
        # Match installed hook meta handlers in either projection tree
        if "hooks" in p and "meta" in p and p.endswith(".py") and "__init__" not in p:
            name = Path(p).name
            if name not in meta_hashes:
                meta_hashes[name] = entry.get("content_hash", "")

    meta_src = source_root / "runtime" / "hooks" / "meta"
    if not meta_src.is_dir():
        return []

    drift: list[str] = []
    for handler in sorted(meta_src.glob("*.py")):
        if handler.name == "__init__.py":
            continue
        recorded = meta_hashes.get(handler.name, "")
        if not recorded:
            continue
        from integrations.manifest import compute_hash as _compute_hash

        if _compute_hash(handler.read_text(encoding="utf-8")) != recorded:
            drift.append(handler.name)
    return drift


def _update_command(
    *, source_root: Path, dream_studio_home: Path | None, dry_run: bool = False
) -> int:
    """Implement ``ds update [--dry-run]``.

    A2.8: replaced the legacy ``subprocess.run(['ds', 'integrate', 'install',
    'claude_code', '--execute'])`` self-shell-out with a direct in-process
    call to ``ClaudeCodeInstaller.install('execute')`` — same pattern as
    the ``ds integrate install`` command path uses today. The shell-out
    spawned a fresh Python interpreter that re-imported the whole CLI
    just to run code that lives in the same process; the direct call
    skips the interpreter overhead, keeps tracebacks intact, and lets
    callers patch the installer with ``unittest.mock``.
    """
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    repo_file = source_root / "VERSION"
    installed_file = paths.dream_studio_home / "state" / "installed-version"

    repo_version = repo_file.read_text(encoding="utf-8").strip() if repo_file.is_file() else None
    if repo_version is None:
        _print({"ok": False, "error": "VERSION file not found in source root"})
        return 1

    installed_version = (
        installed_file.read_text(encoding="utf-8").strip() if installed_file.is_file() else None
    )

    if installed_version == repo_version:
        # Version stamp matches, but check whether canonical hook source has drifted
        # from what the manifest recorded at the last install.  A hook code change
        # without a version bump (e.g. WO-A) must still trigger re-projection.
        from integrations.manifest import read_manifest

        manifest = read_manifest("claude_code", ds_home=paths.dream_studio_home)
        if manifest and _canonical_hook_drift(source_root, manifest):
            pass  # fall through to reinstall
        else:
            _print({"ok": True, "status": "already_current", "version": repo_version})
            return 0

    if dry_run:
        _print(
            {
                "ok": True,
                "status": "update_available",
                "from": installed_version,
                "to": repo_version,
                "dry_run": True,
                "would_run": "ds integrate install claude_code --execute",
            }
        )
        return 0

    from integrations.detector import detect_claude_code
    from integrations.installer.claude_code import ClaudeCodeInstaller
    from integrations.manifest import get_ds_home

    canonical_root = source_root / "canonical"
    ds_home = dream_studio_home or get_ds_home()

    try:
        detected = detect_claude_code()
        installer = ClaudeCodeInstaller(
            detected.config_root,
            detected.scope,
            canonical_root=canonical_root,
            ds_home=ds_home,
        )
        install_result = installer.install("execute")
        install_ok = bool(install_result.get("ok", True))

        # When running from a project-scope dir, also update the user-global surface so
        # both projection trees stay in sync.  The project-scope tree has no hook registrations
        # (dispatch consolidation); the user-global tree is the single dispatch surface.
        if install_ok and detected.scope == "project":
            user_installer = ClaudeCodeInstaller(
                Path.home() / ".claude",
                "user",
                canonical_root=canonical_root,
                ds_home=ds_home,
            )
            user_result = user_installer.install("execute")
            if not user_result.get("ok", True):
                install_result["user_scope_warning"] = user_result
    except Exception as exc:  # noqa: BLE001 — surface the install failure to operator
        install_result = {"ok": False, "error": str(exc), "error_type": type(exc).__name__}
        install_ok = False

    install_output = json.dumps(install_result, indent=2, sort_keys=True)

    if install_ok:
        installed_file.parent.mkdir(parents=True, exist_ok=True)
        installed_file.write_text(repo_version + "\n", encoding="utf-8")

    _print(
        {
            "ok": install_ok,
            "status": "updated" if install_ok else "install_failed",
            "from": installed_version,
            "to": repo_version,
            "changes": install_output,
        }
    )
    return 0 if install_ok else 1


def _repair_plan(*, source_root: Path, dream_studio_home: Path | None) -> dict[str, Any]:
    doctor = _doctor_status(source_root=source_root, dream_studio_home=dream_studio_home)
    actions = []
    if not doctor["checks"]["sqlite_exists"]:
        actions.append("Run ds install --home <explicit-home> --rehearsal for rehearsal setup.")
    if not doctor["checks"]["module_profiles_valid"]:
        actions.append("Review module profile validation errors before runtime update.")
    return {
        "model_name": "dream_studio_repair_plan",
        "derived_view": True,
        "primary_authority": False,
        "repair_executed": False,
        "mutation_authorized": False,
        "delete_authorized": False,
        "actions": actions,
        "status": "pass" if not actions else "attention_required",
        "rollback_guidance": "No rollback required; this command is plan-only.",
    }


def _validate_status(*, source_root: Path, dream_studio_home: Path | None) -> dict[str, Any]:
    from core.health.validate import run_validation

    return run_validation(source_root=source_root, dream_studio_home=dream_studio_home)


def _migrate_command(args: argparse.Namespace) -> int:
    from core.config.sqlite_bootstrap import activate_pending_migrations, pending_migrations_info

    if args.migrate_subcommand == "status":
        pending = pending_migrations_info()
        if not pending:
            return _print(
                {"ok": True, "pending_count": 0, "message": "All merged migrations are activated."}
            )
        return _print(
            {
                "ok": True,
                "pending_count": len(pending),
                "message": (
                    f"{len(pending)} merged migration(s) await activation on the live authority."
                    " Run `ds migrate activate --confirm` to apply."
                ),
                "pending_migrations": pending,
            }
        )

    if args.migrate_subcommand == "activate":
        pending = pending_migrations_info()
        if not pending:
            return _print(
                {"ok": True, "applied": [], "message": "No pending migrations to activate."}
            )

        if not getattr(args, "confirm", False):
            print(f"\n  {len(pending)} migration(s) will be applied to the live authority DB:\n")
            for m in pending:
                print(f"    [{m['version']}] {m['description']}")
            print("\n  A backup will be created before applying.")
            print("  Re-run with --confirm to proceed.\n")
            return 0

        db_path = Path(args.db_path).resolve() if getattr(args, "db_path", None) else None
        result = activate_pending_migrations(db_path)
        return _print(result)

    return 1
