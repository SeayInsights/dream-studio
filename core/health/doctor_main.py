"""Doctor composite entry point — run_doctor_checks().

The pure read-only path is `run_doctor_checks(fix=False)`. The `--fix` path
remains driven from the CLI wrapper in `interfaces/cli/ds.py` because it
shells out to `ds integrate install`, `ds spool ingest`, and `ds update`
which are themselves CLI-bound; A2 will decompose those subprocess
re-invocations into direct calls.

Split out of doctor.py (WO-GF-CORE-HEALTH-SKILLS): composes doctor_skill_sync.py
and doctor_checks.py into the single composite health view used by `ds doctor`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from core.health.overhead import run_overhead_checks
from core.health.validate import run_validation
from core.installed_runtime import resolve_installed_runtime_paths

from .doctor_checks import (
    _check_agents_installed,
    _check_dispatcher_hooks,
    _check_failed_events,
    _check_handoff_spawner,
    _check_hook_freshness,
    _check_stale_dbs,
    _check_version_current,
)
from .doctor_skill_sync import _check_skills_installed


def run_doctor_checks(
    *,
    source_root: Path,
    dream_studio_home: Path | None = None,
    fix: bool = False,
) -> dict[str, Any]:
    """Composite doctor status. fix=True triggers self-healing side effects."""

    validation = run_validation(source_root=source_root, dream_studio_home=dream_studio_home)
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    claude_dir = Path.home() / ".claude"

    dispatcher_ok = _check_dispatcher_hooks(claude_dir)
    skills_info = _check_skills_installed(claude_dir, source_root=source_root)
    agents_info = _check_agents_installed(claude_dir, source_root)
    failed_info = _check_failed_events(paths.dream_studio_home)
    version_info = _check_version_current(source_root, paths.dream_studio_home)
    handoff_spawner_info = _check_handoff_spawner(source_root)
    stale_dbs_info = _check_stale_dbs(paths.dream_studio_home)
    hook_freshness_info = _check_hook_freshness(source_root, claude_dir)

    from core.config.schema_coherence import check_schema_coherence

    # Use the canonical live-DB path (same resolver as database.py).
    # paths.dream_studio_home is already resolved from the env/default chain.
    live_db = paths.dream_studio_home / "state" / "studio.db"
    schema_coherence_info = check_schema_coherence(source_root=source_root, live_db_path=live_db)
    overhead_info = run_overhead_checks(source_root=source_root, claude_dir=claude_dir)

    core_pass = validation["ready"]
    critical_fail = (
        not dispatcher_ok
        or skills_info["missing"]
        or failed_info["count"] >= 6
        or not version_info["current"]
    )
    has_warnings = 0 < failed_info["count"] < 6

    if critical_fail:
        overall = "fail"
    elif not core_pass:
        overall = "attention_required"
    elif has_warnings:
        overall = "warn"
    else:
        overall = "pass"

    fix_actions: list[str] = []
    if fix:
        if (
            not dispatcher_ok
            or skills_info["missing"]
            or agents_info["missing"]
            or hook_freshness_info["stale"]
        ):
            try:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "interfaces.cli.ds",
                        "integrate",
                        "install",
                        "claude_code",
                        "--execute",
                    ],
                    check=False,
                )
                fix_actions.append("install: ran integrate install claude_code --execute")
            except Exception as exc:
                fix_actions.append(f"install: failed — {exc}")
        if failed_info["count"] > 0:
            try:
                spool_events_root = paths.dream_studio_home / "events"
                failed_dir = spool_events_root / "failed"
                spool_dir = spool_events_root / "spool"
                spool_dir.mkdir(parents=True, exist_ok=True)
                requeued = 0
                for event_file in list(failed_dir.glob("*.json")):
                    try:
                        os.replace(str(event_file), str(spool_dir / event_file.name))
                        requeued += 1
                    except OSError:
                        pass
                fix_actions.append(f"requeue: moved {requeued} failed event(s) back to spool/")
            except Exception as exc:
                fix_actions.append(f"requeue: failed — {exc}")
            try:
                subprocess.run(
                    [sys.executable, "-m", "interfaces.cli.ds", "spool", "ingest"],
                    check=False,
                )
                fix_actions.append("spool ingest: ran spool ingest to process requeued events")
            except Exception as exc:
                fix_actions.append(f"spool ingest: failed — {exc}")
        if not version_info["current"]:
            try:
                subprocess.run(
                    [sys.executable, "-m", "interfaces.cli.ds", "update"],
                    check=False,
                )
                fix_actions.append("update: ran ds update")
            except Exception as exc:
                fix_actions.append(f"update: failed — {exc}")

    result: dict[str, Any] = {
        "model_name": "dream_studio_doctor_status",
        "derived_view": True,
        "primary_authority": False,
        "status": overall,
        "checks": {
            "sqlite_exists": validation["sqlite_exists"],
            "schema_version_known": validation["schema_version"] is not None,
            "module_profiles_valid": not validation["module_profile_errors"],
            "doctor_runs_read_only": True,
            "dispatcher_hooks_installed": dispatcher_ok,
            "skills_installed": skills_info,
            "agents_installed": agents_info,
            "failed_events": failed_info,
            "version_current": version_info,
            "schema_coherence": schema_coherence_info,
            "overhead": overhead_info,
            "handoff_spawner": handoff_spawner_info,
            "stale_dbs": stale_dbs_info,
            "hook_freshness": hook_freshness_info,
        },
        "validation": validation,
    }
    if fix:
        result["fix_actions"] = fix_actions
    return result
