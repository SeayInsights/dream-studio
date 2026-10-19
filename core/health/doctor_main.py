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

from core.config.paths import claude_config_root
from core.health.overhead import run_overhead_checks
from core.health.validate import run_validation
from core.installed_runtime import resolve_installed_runtime_paths

from .doctor_checks import (
    _check_agents_installed,
    _check_dispatcher_hooks,
    _check_failed_events,
    _check_handoff_spawner,
    _check_hook_freshness,
    _check_installed_app,
    _check_stale_dbs,
    _check_version_current,
)
from .doctor_skill_sync import _check_skills_installed

#: Runs the ds entry point from an explicit code root (argv[1]); the rest is ds's argv.
_DS_BOOTSTRAP = (
    "import sys; sys.path.insert(0, sys.argv.pop(1)); "
    "from interfaces.cli.ds import main; sys.exit(main(sys.argv[1:]))"
)


def _ds_command(home: Path, *args: str) -> list[str]:
    """The command that re-runs THIS ds (this interpreter, this code root) on *home*.

    `sys.executable -m interfaces.cli.ds` put the working directory first on sys.path,
    so an installed app's repair run inside a checkout executed the checkout; and with
    no --home it repaired the default home rather than the one doctor examined.
    -I drops the working directory and PYTHON* variables, -X utf8 keeps output decodable,
    and the code root is passed explicitly.
    """
    from core.config.paths import code_root

    return [
        sys.executable,
        "-I",
        "-X",
        "utf8",
        "-c",
        _DS_BOOTSTRAP,
        str(code_root()),
        "--home",
        str(home),
        *args,
    ]


def run_doctor_checks(
    *,
    source_root: Path,
    dream_studio_home: Path | None = None,
    fix: bool = False,
    record_counts: bool = False,
    accept_drop: bool = False,
) -> dict[str, Any]:
    """Composite doctor status. fix=True triggers self-healing side effects.

    Without fix or record_counts this writes nothing: every authority read goes through
    a read-only connection and the main-CI cache is read but not written back
    (tests/unit/test_doctor_read_only.py snapshots the home around a run).
    record_counts=True writes the business row counts as the baseline later runs
    compare against (core.health.authority_data).
    """

    validation = run_validation(source_root=source_root, dream_studio_home=dream_studio_home)
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    claude_dir = claude_config_root()

    dispatcher_ok = _check_dispatcher_hooks(claude_dir)
    skills_info = _check_skills_installed(claude_dir, source_root=source_root)
    agents_info = _check_agents_installed(claude_dir, source_root)
    failed_info = _check_failed_events(paths.dream_studio_home)
    version_info = _check_version_current(source_root, paths.dream_studio_home)
    handoff_spawner_info = _check_handoff_spawner(source_root)
    stale_dbs_info = _check_stale_dbs(paths.dream_studio_home)
    hook_freshness_info = _check_hook_freshness(source_root, claude_dir)
    installed_app_info = _check_installed_app(paths.dream_studio_home)

    from core.config.schema_coherence import check_schema_coherence

    # Use the canonical live-DB path (same resolver as database.py).
    # paths.dream_studio_home is already resolved from the env/default chain.
    live_db = paths.dream_studio_home / "state" / "studio.db"
    schema_coherence_info = check_schema_coherence(source_root=source_root, live_db_path=live_db)
    overhead_info = run_overhead_checks(source_root=source_root, claude_dir=claude_dir)

    # WO-BYPASS-TELEMETRY: which enforcement escape hatches fired recently.
    # Informational — bypasses are legitimate operator decisions; INVISIBLE
    # bypasses are the defect this section removes.
    from core.health.doctor_bypass import bypass_audit

    bypass_audit_info = bypass_audit(live_db)

    from core.health.authority_data import authority_data_check
    from core.health.authority_data import record_counts as _record_counts

    from core.health.authority_data import drops

    authority_data_info = authority_data_check(paths.dream_studio_home, live_db)
    record_refused = None
    if record_counts and authority_data_info["readable"]:
        if drops(authority_data_info) and not accept_drop:
            record_refused = (
                "not recorded: the counts dropped since the last baseline "
                f"({'; '.join(drops(authority_data_info))}). Find out why first; to record "
                "the smaller numbers as the new baseline anyway, add --accept-drop."
            )
        else:
            authority_data_info["recorded"] = _record_counts(paths.dream_studio_home, live_db)
            authority_data_info = {
                **authority_data_check(paths.dream_studio_home, live_db),
                "recorded": authority_data_info["recorded"],
            }
    if record_refused:
        authority_data_info["record_refused"] = record_refused

    # WO-MAINRED-VISIBILITY: the post-merge full-ci verdict for main. pr-smoke
    # green is merge authorization, not proof main is green — and main sat red
    # across eight merges on 2026-08-19 because nothing reported it. Advisory:
    # a red main never fails the doctor (someone else's red must not block work),
    # it just stops being invisible.
    from core.health.main_ci import CACHE_MAX_AGE_SECONDS, main_ci_status, main_ci_warning

    # WO-MAINCI-CACHE: the doctor accepts a recent cached answer. It is run often
    # and is otherwise entirely local, so paying a gh round trip (up to 25s when
    # gh is unreachable) every time was the wrong trade for a signal that changes
    # on the order of tens of minutes. A cached result states its age.
    #
    # Gap WO 094f3c12 (partial_failure, named by the falsification analyst): this
    # is the LAST check in the report and the only one that leaves the machine, so
    # an exception here discards every check already computed and hands the operator
    # a traceback instead of a doctor payload. The reader is built not to raise, but
    # "built not to" is what was believed before a TypeError from it took main red
    # for a day. An advisory check earns no right to abort the report around it.
    from core.config.paths import is_source_checkout

    try:
        if not is_source_checkout(source_root):
            # An installed app has no repository to ask about; main's CI is a
            # development signal for a checkout.
            raise LookupError(f"{source_root} is an installed app, not a source checkout")
        main_ci_info = main_ci_status(
            repo_root=source_root,
            max_age_seconds=CACHE_MAX_AGE_SECONDS,
            db_path=live_db,
            write_cache=False,
        )
        _main_ci_warning = main_ci_warning(main_ci_info)
        if _main_ci_warning:
            main_ci_info["warning"] = _main_ci_warning
    except Exception as exc:  # noqa: BLE001 - advisory: report the failure, never propagate it
        main_ci_info = {
            "status": "unknown",
            "red": False,
            "reason": f"main CI status could not be read: {type(exc).__name__}: {exc}"[:200],
        }

    core_pass = validation["ready"]
    critical_fail = (
        not dispatcher_ok
        or skills_info["missing"]
        or failed_info["count"] >= 6
        or version_info["current"] is False
    )
    has_warnings = 0 < failed_info["count"] < 6

    # Data at risk: an authority_data or installed_app warning (a drop, a missing table, a
    # lost authority, a ds that is not the installed app) is never a pass.
    authority_attention = bool(
        authority_data_info["warnings"]
        or installed_app_info["warnings"]
        or authority_data_info.get("record_refused")
    )
    if critical_fail:
        overall = "fail"
    elif authority_attention:
        overall = "attention_required"
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
                # The root this doctor examined, named explicitly: integrate would
                # otherwise resolve one itself, and from a working directory inside some
                # repository it would also write that repository's git pre-push hook.
                subprocess.run(
                    _ds_command(
                        paths.dream_studio_home,
                        "integrate",
                        "install",
                        "claude_code",
                        "--config-root",
                        str(claude_dir),
                    )
                    + ["--execute"],
                    check=False,
                )
                fix_actions.append(
                    f"install: ran integrate install claude_code --config-root {claude_dir} "
                    "--execute"
                )
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
                    _ds_command(paths.dream_studio_home, "spool", "ingest"),
                    check=False,
                )
                fix_actions.append("spool ingest: ran spool ingest to process requeued events")
            except Exception as exc:
                fix_actions.append(f"spool ingest: failed — {exc}")
        if version_info["current"] is False:
            try:
                subprocess.run(
                    _ds_command(paths.dream_studio_home, "update"),
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
        "authority_attention": authority_attention,
        "checks": {
            "sqlite_exists": validation["sqlite_exists"],
            "schema_version_known": validation["schema_version"] is not None,
            "module_profiles_valid": not validation["module_profile_errors"],
            "doctor_runs_read_only": not (fix or record_counts),
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
            "bypass_audit": bypass_audit_info,
            "installed_app": installed_app_info,
            "authority_data": authority_data_info,
            "main_ci": main_ci_info,
        },
        "validation": validation,
    }
    if fix:
        result["fix_actions"] = fix_actions
    return result
