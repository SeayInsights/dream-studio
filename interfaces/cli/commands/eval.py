"""ds eval command group — behavioral eval runner (18.8.3)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from interfaces.cli.cli_utils import _print, _table_exists_in_conn

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``eval`` subparser tree to *subcommands*."""
    eval_cmd = subcommands.add_parser("eval", help="Behavioral eval runner (18.8.3)")
    eval_sub = eval_cmd.add_subparsers(dest="eval_command", required=True)

    eval_run_cmd = eval_sub.add_parser("run", help="Run behavioral evals")
    eval_run_cmd.add_argument("--all", action="store_true", default=False, help="Run all evals")
    eval_run_cmd.add_argument(
        "--eval-id", default=None, dest="eval_id", help="Run a specific eval by ID"
    )
    eval_run_cmd.add_argument(
        "--skill", default=None, dest="skill_filter", help="Filter evals by skill_id"
    )
    eval_run_cmd.add_argument(
        "--evals-dir", default=None, dest="evals_dir", help="Override evals directory"
    )
    eval_run_cmd.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Live mode: spawn a fresh claude subprocess and score its events (requires claude CLI in PATH)",
    )

    eval_baseline_cmd = eval_sub.add_parser("baseline", help="Print current baseline scores")
    eval_baseline_cmd.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Run eval in live mode and capture the result as the live baseline (requires --eval-id)",
    )
    eval_baseline_cmd.add_argument(
        "--eval-id",
        default=None,
        dest="eval_id",
        help="Eval ID to capture live baseline for (required when --live is specified)",
    )

    eval_compare_cmd = eval_sub.add_parser(
        "compare", help="Compare recent run scores against baseline"
    )
    eval_compare_cmd.add_argument(
        "--eval-id", default=None, dest="eval_id", help="Compare specific eval"
    )

    eval_list_cmd = eval_sub.add_parser("list", help="List available eval cases")
    eval_list_cmd.add_argument(
        "--skill", default=None, dest="skill_filter", help="Filter by skill_id"
    )
    eval_list_cmd.add_argument(
        "--evals-dir", default=None, dest="evals_dir", help="Override evals directory"
    )

    eval_registry_cmd = eval_sub.add_parser(
        "registry", help="Unified eval registry across skills, hooks, workflows, agents"
    )
    eval_registry_sub = eval_registry_cmd.add_subparsers(dest="registry_command", required=True)
    eval_registry_list_cmd = eval_registry_sub.add_parser(
        "list", help="List all registered eval targets with latest status"
    )
    eval_registry_list_cmd.add_argument(
        "--type",
        default=None,
        dest="target_type",
        choices=["skill", "hook", "workflow", "agent"],
        help="Filter by target type",
    )
    eval_registry_show_cmd = eval_registry_sub.add_parser(
        "show", help="Show eval run history for a specific target"
    )
    eval_registry_show_cmd.add_argument("target_id", help="Target ID to inspect")

    eval_queue_cmd = eval_sub.add_parser(
        "queue", help="Friction-flagged re-run queue: show pending evals or run them"
    )
    eval_queue_sub = eval_queue_cmd.add_subparsers(dest="queue_command", required=True)
    eval_queue_sub.add_parser("show", help="Show eval targets pending re-run (friction_flag=1)")
    eval_queue_sub.add_parser(
        "run",
        help="Run live evals for all friction-flagged targets and clear their flags on pass",
    )
    eval_queue_sub.add_parser(
        "aggregate", help="Aggregate friction signals from raw_sessions, corrections, guardrails"
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(args: argparse.Namespace, *, source_root: Path) -> int:
    """Dispatch ds eval {run,baseline,compare,list,registry,queue} commands (18.8.3)."""
    from core.eval.runner import EvalRunner, format_results_report, load_eval_cases

    evals_dir = Path(args.evals_dir) if getattr(args, "evals_dir", None) else source_root / "evals"

    if args.eval_command == "list":
        cases = load_eval_cases(evals_dir)
        skill = getattr(args, "skill_filter", None)
        if skill:
            cases = [c for c in cases if c.skill_id == skill]
        rows = [
            {
                "eval_id": c.eval_id,
                "version": c.version,
                "skill_id": c.skill_id,
                "description": c.description,
            }
            for c in cases
        ]
        return _print({"evals": rows, "count": len(rows)})

    if args.eval_command == "run":
        runner = EvalRunner(evals_dir=evals_dir)
        eval_id = getattr(args, "eval_id", None)
        skill_filter = getattr(args, "skill_filter", None)
        run_all = getattr(args, "all", False)
        live_mode = getattr(args, "live", False)
        if eval_id:
            from core.eval.schema import EvalCase

            path = evals_dir / f"{eval_id}.json"
            if not path.exists():
                print(
                    json.dumps({"ok": False, "error": f"Eval not found: {eval_id}"}),
                    file=sys.stderr,
                )
                return 1
            case = EvalCase.from_json(path)
            result = runner.run_case(case, live=live_mode)
            out: dict = {
                "eval_id": result.eval_id,
                "passed": result.passed,
                "composite_score": result.composite_score,
                "event_score": result.event_score,
                "behavior_score": getattr(result, "behavior_score", None),
                "run_mode": result.run_mode,
            }
            if live_mode:
                out["delta_from_fixture_baseline"] = round(
                    (result.baseline_score or 0) - result.composite_score, 4
                )
                out["failure_reasons"] = list(
                    result.match_result.missing_events + result.match_result.negative_violations
                )
            return _print(out)
        if run_all or skill_filter:
            results = runner.run_all(skill_filter=skill_filter, live=live_mode)
            report = format_results_report(results)
            print(report)
            passed = sum(1 for r in results if r.passed)
            return 0 if passed == len(results) else 1
        print("Specify --all, --eval-id, or --skill to run evals.", file=sys.stderr)
        return 1

    if args.eval_command == "baseline":
        live_mode = getattr(args, "live", False)
        eval_id = getattr(args, "eval_id", None)
        if live_mode:
            if not eval_id:
                print("--eval-id is required when --live is specified", file=sys.stderr)
                return 1
            from core.eval.schema import EvalCase

            path = evals_dir / f"{eval_id}.json"
            if not path.exists():
                print(
                    json.dumps({"ok": False, "error": f"Eval not found: {eval_id}"}),
                    file=sys.stderr,
                )
                return 1
            case = EvalCase.from_json(path)
            runner = EvalRunner(evals_dir=evals_dir)
            result = runner.run_case(case, live=True)
            from core.eval.baseline import load_baseline

            live_baseline = load_baseline(eval_id + ":live", case.version)
            return _print(
                {
                    "eval_id": eval_id,
                    "live_baseline_score": (
                        live_baseline["baseline_score"] if live_baseline else result.composite_score
                    ),
                    "passed": result.passed,
                    "run_mode": result.run_mode,
                }
            )
        from core.eval.baseline import get_all_baselines

        rows = get_all_baselines()
        return _print({"baselines": rows, "count": len(rows)})

    if args.eval_command == "compare":
        from core.eval.baseline import load_baseline

        eval_id = getattr(args, "eval_id", None)
        if not eval_id:
            print("--eval-id required for compare", file=sys.stderr)
            return 1
        baseline = load_baseline(eval_id, "1.0.0")
        if baseline is None:
            print(json.dumps({"ok": False, "error": f"No baseline for {eval_id}"}), file=sys.stderr)
            return 1
        return _print({"eval_id": eval_id, "baseline": baseline})

    if args.eval_command == "registry":
        return _eval_registry_dispatch(args, source_root=source_root)

    if args.eval_command == "queue":
        return _eval_queue_dispatch(args, evals_dir=evals_dir)

    print(f"Unknown eval command: {args.eval_command}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


def _eval_registry_dispatch(args: argparse.Namespace, *, source_root: Path) -> int:
    """Dispatch ds eval registry {list,show} commands (WO-EVAL-REGISTRY)."""
    import sqlite3

    from core.config.database import DatabaseRuntime

    db_path = DatabaseRuntime.get_instance().db_path

    registry_command = getattr(args, "registry_command", None)

    if registry_command == "list":
        target_type = getattr(args, "target_type", None)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if not _table_exists_in_conn(conn, "eval_registry"):
                return _print(
                    {"ok": False, "error": "eval_registry table not found. Run migrations."}
                )
            where = "WHERE er.target_type = ?" if target_type else ""
            params = [target_type] if target_type else []
            # "passed" now comes from the eval.run.completed / work_order.verified
            # canonical event whose payload.run_id matches er.last_run_id — the
            # ds_eval_runs/hook_eval_runs LEFT JOINs were dropped in T4. No match
            # (e.g. last_run_id is NULL, or the run predates canonical emission)
            # leaves passed NULL, same as before.
            rows = conn.execute(
                f"""
                SELECT
                    er.eval_id,
                    er.target_type,
                    er.target_id,
                    er.rubric_score,
                    er.last_run_at,
                    er.friction_flag,
                    json_extract(bce.payload, '$.passed') AS passed
                FROM eval_registry er
                LEFT JOIN business_canonical_events bce
                    ON bce.event_type IN ('eval.run.completed', 'work_order.verified')
                    AND json_extract(bce.payload, '$.run_id') = er.last_run_id
                {where}
                ORDER BY er.target_type, er.target_id
                """,
                params,
            ).fetchall()
        result = [
            {
                "eval_id": r["eval_id"],
                "target_type": r["target_type"],
                "target_id": r["target_id"],
                "rubric_score": r["rubric_score"],
                "last_run_at": r["last_run_at"],
                "passed": "Y" if r["passed"] else ("N" if r["passed"] is not None else "—"),
                "friction_flag": bool(r["friction_flag"]),
            }
            for r in rows
        ]
        return _print({"registry": result, "count": len(result)})

    if registry_command == "show":
        target_id = getattr(args, "target_id", None)
        if not target_id:
            print("target_id required", file=sys.stderr)
            return 1
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if not _table_exists_in_conn(conn, "eval_registry"):
                return _print(
                    {"ok": False, "error": "eval_registry table not found. Run migrations."}
                )
            entry = conn.execute(
                "SELECT * FROM eval_registry WHERE target_id = ?", (target_id,)
            ).fetchone()
            if entry is None:
                return _print(
                    {"ok": False, "error": f"No registry entry for target_id={target_id!r}"}
                )
            # Fetch run history from canonical events (T4 dropped ds_eval_runs /
            # hook_eval_runs). Hooks wrote eval_id as 'hook:<hook_id>'; other
            # target types matched eval_id directly to target_id.
            target_type = entry["target_type"]
            eval_id_filter = f"hook:{target_id}" if target_type == "hook" else target_id
            history_rows = conn.execute(
                """
                SELECT payload, event_timestamp
                FROM business_canonical_events
                WHERE event_type IN ('eval.run.completed', 'work_order.verified')
                  AND json_extract(payload, '$.eval_id') = ?
                ORDER BY event_timestamp DESC
                LIMIT 20
                """,
                (eval_id_filter,),
            ).fetchall()
            if target_type == "hook":
                run_rows = [
                    {
                        "run_id": p.get("run_id"),
                        "eval_type": p.get("eval_type"),
                        "passed": p.get("passed"),
                        "score": p.get("score"),
                        "failure_reasons": p.get("failure_reasons"),
                        "created_at": p.get("created_at", ts),
                    }
                    for (p, ts) in (
                        (
                            json.loads(row["payload"]) if row["payload"] else {},
                            row["event_timestamp"],
                        )
                        for row in history_rows
                    )
                ]
            else:
                run_rows = [
                    {
                        "run_id": p.get("run_id"),
                        "eval_id": p.get("eval_id"),
                        "eval_version": p.get("eval_version"),
                        "total_score": p.get("total_score"),
                        "passed": p.get("passed"),
                        "failure_reasons": p.get("failure_reasons"),
                        "started_at": p.get("started_at", ts),
                        "completed_at": p.get("completed_at", ts),
                    }
                    for (p, ts) in (
                        (
                            json.loads(row["payload"]) if row["payload"] else {},
                            row["event_timestamp"],
                        )
                        for row in history_rows
                    )
                ]
        return _print(
            {
                "target_id": target_id,
                "target_type": target_type,
                "rubric_score": entry["rubric_score"],
                "last_run_at": entry["last_run_at"],
                "friction_flag": bool(entry["friction_flag"]),
                "runs": run_rows,
            }
        )

    print(f"Unknown registry command: {registry_command}", file=sys.stderr)
    return 1


def _eval_queue_dispatch(args: argparse.Namespace, *, evals_dir: Path) -> int:
    """Dispatch ds eval queue {show,run,aggregate} commands (WO-EVAL-LOOP)."""
    import sqlite3

    from core.config.database import DatabaseRuntime

    db_path = DatabaseRuntime.get_instance().db_path
    queue_command = getattr(args, "queue_command", None)

    if queue_command == "aggregate":
        from core.eval.friction import aggregate_friction_signals

        result = aggregate_friction_signals(db_path=db_path)
        return _print(result)

    if queue_command == "show":
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if not _table_exists_in_conn(conn, "eval_registry"):
                return _print(
                    {"ok": False, "error": "eval_registry table not found. Run migrations."}
                )
            rows = conn.execute("""
                SELECT eval_id, target_type, target_id, rubric_score,
                       last_run_at, friction_flag, pending_rerun, updated_at
                FROM eval_registry
                WHERE pending_rerun = 1
                ORDER BY updated_at DESC
                """).fetchall()
        return _print({"pending_rerun": [dict(r) for r in rows], "count": len(rows)})

    if queue_command == "run":
        from core.eval.runner import EvalRunner
        from core.eval.schema import EvalCase

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if not _table_exists_in_conn(conn, "eval_registry"):
                return _print(
                    {"ok": False, "error": "eval_registry table not found. Run migrations."}
                )
            pending = conn.execute(
                "SELECT target_id, target_type FROM eval_registry WHERE pending_rerun = 1"
            ).fetchall()

        runner = EvalRunner(evals_dir=evals_dir)
        results = []
        for row in pending:
            target_id = row["target_id"]
            path = evals_dir / f"{target_id}.json"
            if not path.exists():
                results.append(
                    {"target_id": target_id, "status": "skipped", "reason": "eval case not found"}
                )
                continue
            case = EvalCase.from_json(path)
            result = runner.run_case(case, live=True)
            if result.passed:
                with sqlite3.connect(db_path) as conn:
                    conn.execute(
                        "UPDATE eval_registry"
                        " SET friction_flag=0, pending_rerun=0, updated_at=datetime('now')"
                        " WHERE target_id=?",
                        (target_id,),
                    )
            results.append(
                {
                    "target_id": target_id,
                    "passed": result.passed,
                    "composite_score": result.composite_score,
                    "friction_cleared": result.passed,
                }
            )
        return _print({"results": results, "count": len(results)})

    print(f"Unknown queue command: {queue_command}", file=sys.stderr)
    return 1
