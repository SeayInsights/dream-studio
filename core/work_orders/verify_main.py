"""Score computation and the ``verify_work_order`` entry point.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the
composite-score computation and the main orchestrator that reads a work
order's tasks, collects git/authority evidence, runs the parallel graders,
computes scores, spawns gap work orders, and persists the verdict. No logic
changes — extracted verbatim from the original module.

Entry point: ``verify_work_order(work_order_id=, source_root=, dream_studio_home=)``.

Architecture (T4c/T4d/T4e):
Four independent graders run in parallel via subprocess.Popen. Each grader is
blind to the other graders' domain — no shared context between prompts:

  Grader 1 — Completion: task list + git diff.
    Returns: {passed, tasks_verified, summary, gaps, completion_score}

  Grader 2 — Correctness: architectural rules + git diff only (NO task list).
    Returns: {correctness_passed, correctness_score, violations, coverage_gaps,
              migration_gaps}

  Grader 3 — Quality: quality best-practice rules + git diff only (NO task list).
    Returns: {quality_passed, quality_score, issues}

  Grader 4 — Migration (only when diff contains migration files): migration SQL
    file contents only (NO task list, NO other diff).
    Returns: {migration_safe, migration_score, risks}

Overall pass = completion_passed AND correctness_passed AND composite >= 0.70
  AND migration_safe (when applicable).

Composite score = (completion * 0.5) + (correctness * 0.3) + (quality * 0.2).

Thresholds:
  >= 0.85: auto-continue to next WO
  0.70-0.84: auto-continue with logged warning
  < 0.70: register remediation WO, do NOT auto-continue

Set DREAM_STUDIO_VERIFY_MOCK=1 to substitute deterministic fixtures for CI.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect

from .verify_db import (
    _read_tasks,
    _read_work_order,
    _require_db,
    _run_sql_checks,
    _format_sql_checks,
)
from .verify_executor import run_executable_checks
from .verify_gaps import (
    _filter_invented_threshold_gaps,
    _insert_gap_work_orders,
    _migration_risks_to_gaps,
    _quality_issues_to_gaps,
    _violations_to_gaps,
)
from .verify_git import _authority_evidence, _find_migration_files
from .verify_persist import _persist_review_verdict, _write_eval_run
from .verify_prompts import (
    _COMPLETION_PROMPT_TEMPLATE,
    _CORRECTNESS_PROMPT_TEMPLATE,
    _MIGRATION_PROMPT_TEMPLATE,
    _QUALITY_PROMPT_TEMPLATE,
)
from .verify_shared import _MOCK_COMPLETION, _MOCK_CORRECTNESS, _MOCK_ENV, _MOCK_QUALITY

# ── Score computation ───────────────────────────────────────────────────────────


def _compute_scores(
    completion: dict[str, Any],
    correctness: dict[str, Any],
    quality: dict[str, Any],
    total_tasks: int,
) -> dict[str, float]:
    # Completion score — grader may return it directly or we compute from tasks_verified.
    raw_completion = completion.get("completion_score")
    if raw_completion is not None:
        completion_score = float(raw_completion)
    elif total_tasks > 0:
        tasks_passed = sum(
            1 for t in completion.get("tasks_verified", []) if t.get("verdict") == "pass"
        )
        completion_score = tasks_passed / total_tasks
    else:
        completion_score = 1.0 if completion.get("passed", True) else 0.0

    # Correctness score.
    raw_correctness = correctness.get("correctness_score")
    if raw_correctness is not None:
        correctness_score = float(raw_correctness)
    else:
        violations = correctness.get("violations", [])
        correctness_score = max(0.0, 1.0 - len(violations) / 7.0) if violations else 1.0

    # Quality score — returned directly by grader.
    quality_score = float(quality.get("quality_score", 1.0))

    composite = (completion_score * 0.5) + (correctness_score * 0.3) + (quality_score * 0.2)

    return {
        "completion_score": round(completion_score, 4),
        "correctness_score": round(correctness_score, 4),
        "quality_score": round(quality_score, 4),
        "composite_score": round(composite, 4),
    }


# ── Main entry point ────────────────────────────────────────────────────────────


def verify_work_order(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
) -> dict[str, Any]:
    """Run parallel independent verification for a work order.

    Returns::

        {
            "ok": bool,
            "work_order_id": str,
            "passed": bool,
            "summary": str,
            "completion": {...},        # grader 1 result
            "correctness": {...},       # grader 2 result
            "quality": {...},           # grader 3 result
            "migration": {...} | None,  # grader 4 result (migration-class only)
            "scores": {
                "completion_score": float,
                "correctness_score": float,
                "quality_score": float,
                "composite_score": float,
            },
            "gaps": [...],              # all combined gaps
            "spawned_work_orders": [...],
            "verdict_path": str,
            "auto_continue_warning": str | None,
        }
    """
    started_at = datetime.now(UTC).isoformat()
    p_root = planning_root or Path.cwd() / ".planning"
    db_path = _require_db(source_root, dream_studio_home)

    with _connect(db_path) as conn:
        wo = _read_work_order(conn, work_order_id)
        if wo is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}

        tasks = _read_tasks(conn, work_order_id)
        if not tasks:
            return {"ok": False, "error": f"No tasks found for work order: {work_order_id}"}

        sql_check_results = _run_sql_checks(tasks, db_path)

        task_list_str = "\n".join(
            "{n}. [{st}] {title}: {desc}{ac}{sql}".format(
                n=i + 1,
                st=t["status"],
                title=t["title"],
                desc=t["description"],
                ac=(
                    f"\n   Acceptance criteria: {t['acceptance_criteria']}"
                    if t.get("acceptance_criteria")
                    else ""
                ),
                sql=_format_sql_checks(sql_check_results.get(t["title"], [])),
            )
            for i, t in enumerate(tasks)
        )
        # Lazy import (not module-level): keeps `_collect_git_commits` a bare-name
        # call resolved against verify_git's live globals on every invocation, so
        # `patch("core.work_orders.verify_git._collect_git_commits", ...)` in tests
        # intercepts it — a static top-level import would freeze the reference at
        # verify_main import time and silently bypass the patch.
        from .verify_git import _collect_git_commits

        git_diff = _collect_git_commits(source_root, work_order_id, title=wo["title"])

        # WO-FIX-VERIFY-GATE: commit-grep by WO id/title fails for every
        # squash-merged WO (the id never survives the squash), forcing force=True
        # or a wo-<shortid> branch-pointer hack. When _collect_git_commits finds
        # nothing, fall back to the WO's executable AC results (SQL/TEST/API-CHECK)
        # as objective, authority-recorded proof — the certification basis that
        # does not depend on commit messages. This is WO-scoped (the WO's own
        # tasks' checks), unlike a whole-repo working diff which would pick up
        # ambient changes. Only when there is NO commit evidence AND no passing
        # executable check is the work genuinely unreviewable (no-false-done).
        #
        # An escalated WO (its originating symptom regressed) must not certify from
        # its own executable AC alone — that is the same check that may have passed
        # before the regression. Escalated work demands a genuine re-review, so the
        # authority-evidence fallback is suppressed and it stays unreviewable until a
        # real (diff-backed or human) verdict clears it.
        from core.work_orders.escalation import read_escalation

        _is_escalated = read_escalation(work_order_id, db_path=db_path) is not None

        authority_certified = False
        if git_diff is None and not _is_escalated:
            ac_results = run_executable_checks(tasks, db_path)
            evidence_text, has_passing = _authority_evidence(work_order_id, tasks, ac_results)
            if has_passing:
                git_diff = evidence_text
                authority_certified = True

        if git_diff is None and not os.environ.get(_MOCK_ENV):
            token = wo["title"].split(" - ")[0].strip()
            warning = (
                f"independent review unreviewable: no commits found referencing "
                f"{work_order_id[:8]} or '{token}'. Work is NOT certified — review manually."
            )
            scores = {
                "completion_score": 0.0,
                "correctness_score": 0.0,
                "quality_score": 0.0,
                "composite_score": 0.0,
            }
            completed_at = datetime.now(UTC).isoformat()
            _write_eval_run(
                conn,
                work_order_id=work_order_id,
                scores=scores,
                passed=False,
                failure_reasons=["unreviewable_no_commits_found"],
                started_at=started_at,
                completed_at=completed_at,
                status="unreviewable",
            )
            verdict_path = _persist_review_verdict(
                work_order_id,
                {
                    "work_order_id": work_order_id,
                    "passed": False,
                    "unreviewable": True,
                    "unreviewable_reason": warning,
                    "scores": scores,
                    "auto_continue_warning": warning,
                    "completion": {},
                    "correctness": {},
                    "quality": {},
                    "gaps": [],
                    "spawned_work_orders": [],
                    "verified_at": completed_at,
                },
                planning_root=p_root,
                db_path=db_path,
            )
            return {
                "ok": True,
                "work_order_id": work_order_id,
                "passed": False,
                "unreviewable": True,
                "summary": warning,
                "completion": {},
                "correctness": {},
                "quality": {},
                "migration": None,
                "scores": scores,
                "auto_continue_warning": warning,
                "gaps": [],
                "spawned_work_orders": [],
                "verdict_path": str(verdict_path) if verdict_path else None,
            }
        if git_diff is None:
            git_diff = f"(no commits found referencing {work_order_id[:8]})"

        # Build grader prompts.
        prompts: dict[str, str] = {
            "completion": _COMPLETION_PROMPT_TEMPLATE.format(
                title=wo["title"],
                work_order_id=work_order_id,
                work_order_type=wo.get("work_order_type", "infrastructure"),
                task_list=task_list_str,
                git_diff=git_diff,
            ),
            "correctness": _CORRECTNESS_PROMPT_TEMPLATE.format(git_diff=git_diff),
            "quality": _QUALITY_PROMPT_TEMPLATE.format(git_diff=git_diff),
        }

        # Grader 4: migration — only when diff includes migration SQL files.
        migration_files = _find_migration_files(source_root, git_diff)
        if migration_files:
            mf = migration_files[0]
            try:
                migration_sql = mf.read_text(encoding="utf-8")
            except Exception:
                migration_sql = "(could not read migration file)"
            prompts["migration"] = _MIGRATION_PROMPT_TEMPLATE.format(
                migration_file=mf.name,
                migration_sql=migration_sql,
            )

        # Run all graders in parallel.
        # Lazy import (not module-level) — see the `_collect_git_commits` note above;
        # keeps `patch("core.work_orders.verify_graders._run_graders_parallel", ...)`
        # able to intercept this call.
        from .verify_graders import _run_graders_parallel

        grader_results = _run_graders_parallel(prompts)

        completion = grader_results.get("completion", _MOCK_COMPLETION.copy())
        correctness = grader_results.get("correctness", _MOCK_CORRECTNESS.copy())
        quality = grader_results.get("quality", _MOCK_QUALITY.copy())
        migration: dict[str, Any] | None = grader_results.get("migration")

        # T1/T3: Detect unreviewable graders (empty LLM output after retry).
        # Record and surface a warning instead of scoring — there is nothing to
        # remediate and spawning gap WOs for an empty diff would be unactionable.
        # Mock mode bypasses this so CI fixtures keep exercising the grader path.
        unreviewable_graders = [
            name
            for name in ("completion", "correctness", "quality", "migration")
            if name in grader_results and grader_results[name].get("unreviewable")
        ]
        if unreviewable_graders and not os.environ.get(_MOCK_ENV):
            reason_str = ", ".join(unreviewable_graders)
            warning = (
                f"independent review unreviewable: grader(s) [{reason_str}] returned empty output. "
                f"Work is NOT certified — review manually."
            )
            scores = {
                "completion_score": 0.0,
                "correctness_score": 0.0,
                "quality_score": 0.0,
                "composite_score": 0.0,
            }
            completed_at = datetime.now(UTC).isoformat()
            _write_eval_run(
                conn,
                work_order_id=work_order_id,
                scores=scores,
                passed=False,
                failure_reasons=["unreviewable_grader_no_summary"],
                started_at=started_at,
                completed_at=completed_at,
                status="unreviewable",
            )
            verdict_path = _persist_review_verdict(
                work_order_id,
                {
                    "work_order_id": work_order_id,
                    "passed": False,
                    "unreviewable": True,
                    "unreviewable_graders": unreviewable_graders,
                    "unreviewable_reason": warning,
                    "scores": scores,
                    "auto_continue_warning": warning,
                    "completion": completion,
                    "correctness": correctness,
                    "quality": quality,
                    "gaps": [],
                    "spawned_work_orders": [],
                    "verified_at": completed_at,
                },
                planning_root=p_root,
                db_path=db_path,
            )
            return {
                "ok": True,
                "work_order_id": work_order_id,
                "passed": False,
                "unreviewable": True,
                "unreviewable_graders": unreviewable_graders,
                "summary": warning,
                "completion": completion,
                "correctness": correctness,
                "quality": quality,
                "migration": migration,
                "scores": scores,
                "auto_continue_warning": warning,
                "gaps": [],
                "spawned_work_orders": [],
                "verdict_path": str(verdict_path) if verdict_path else None,
            }

        # Compute scores.
        scores = _compute_scores(completion, correctness, quality, total_tasks=len(tasks))
        composite = scores["composite_score"]

        # Determine individual pass/fail signals.
        completion_passed = completion.get("passed", False)
        correctness_passed = correctness.get("correctness_passed", True)
        migration_safe = migration.get("migration_safe", True) if migration else True

        # Collect all gaps from all graders.
        all_gaps: list[dict[str, Any]] = []
        all_gaps.extend(completion.get("gaps", []))

        if not correctness_passed:
            all_gaps.extend(
                _violations_to_gaps(
                    correctness.get("violations", []),
                    correctness.get("coverage_gaps", []),
                    correctness.get("migration_gaps", []),
                )
            )

        if composite < 0.70:
            quality_errors = [i for i in quality.get("issues", []) if i.get("severity") == "error"]
            all_gaps.extend(_quality_issues_to_gaps(quality_errors))

        if migration and not migration_safe:
            all_gaps.extend(_migration_risks_to_gaps(migration.get("risks", [])))

        # Overall pass/fail.
        passed = completion_passed and correctness_passed and composite >= 0.70 and migration_safe

        auto_continue_warning: str | None = None
        if passed and composite < 0.85:
            auto_continue_warning = (
                f"Quality warning: composite score {composite:.2f} is below 0.85. "
                "Auto-continuing but recommend addressing quality issues."
            )

        # Collect failure reasons for eval_runs.
        failure_reasons: list[str] = []
        if not completion_passed:
            failure_reasons.append(f"completion_failed (score={scores['completion_score']:.2f})")
        if not correctness_passed:
            failure_reasons.append(f"correctness_failed (score={scores['correctness_score']:.2f})")
        if composite < 0.70:
            failure_reasons.append(f"composite_below_threshold ({composite:.2f} < 0.70)")
        if not migration_safe:
            failure_reasons.append("migration_unsafe")

        # T2: reject gaps that invent a numeric threshold absent from the AC text.
        acceptance_text = " ".join(
            f"{t.get('title', '')} {t.get('description', '')} {t.get('acceptance_criteria', '')}"
            for t in tasks
        )
        all_gaps = _filter_invented_threshold_gaps(all_gaps, acceptance_text)

        # Register gap WOs. milestone_id is no longer required (T3): null-milestone
        # gaps still spawn and dedup, scoped by project_id.
        spawned: list[dict[str, Any]] = []
        if all_gaps and wo.get("project_id"):
            spawned = _insert_gap_work_orders(
                conn,
                gaps=all_gaps,
                project_id=wo["project_id"],
                milestone_id=wo.get("milestone_id"),
                reviewed_work_order_id=work_order_id,
                reviewed_wo_title=wo["title"],
                reviewed_wo_sequence=wo.get("sequence_order"),
            )

        completed_at = datetime.now(UTC).isoformat()

        # Write eval run.
        _write_eval_run(
            conn,
            work_order_id=work_order_id,
            scores=scores,
            passed=passed,
            failure_reasons=failure_reasons,
            started_at=started_at,
            completed_at=completed_at,
        )

        # WO-FILESDB-C2: DB-first verdict persistence (authority, kind=review_verdict);
        # .planning disk only as the unreleased-migration fallback. Supersedes the
        # WO-FILESDB-P1 disk+DB dual-write.
        full_verdict: dict[str, Any] = {
            "work_order_id": work_order_id,
            "passed": passed,
            "scores": scores,
            "auto_continue_warning": auto_continue_warning,
            "completion": completion,
            "correctness": correctness,
            "quality": quality,
            "gaps": all_gaps,
            "spawned_work_orders": spawned,
            "certification_basis": "authority_evidence" if authority_certified else "git_diff",
            "verified_at": completed_at,
        }
        if migration is not None:
            full_verdict["migration"] = migration
        verdict_path = _persist_review_verdict(
            work_order_id, full_verdict, planning_root=p_root, db_path=db_path
        )

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "passed": passed,
        "summary": completion.get("summary", ""),
        "completion": completion,
        "correctness": correctness,
        "quality": quality,
        "migration": migration,
        "scores": scores,
        "auto_continue_warning": auto_continue_warning,
        "gaps": all_gaps,
        "spawned_work_orders": spawned,
        "certification_basis": "authority_evidence" if authority_certified else "git_diff",
        "verdict_path": str(verdict_path) if verdict_path else None,
    }
