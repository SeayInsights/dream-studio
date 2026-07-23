"""Outcome eval (WO-OUTCOME-EVAL) — re-run a closed WO's originating symptom + ACs.

The process eval runner (runner_process.py) measures PROCESS (rail adherence
from traces). The outcome eval measures OUTCOME: for a recently-closed WO,
re-run its originating_symptom + task acceptance-criteria against live/seeded
state and report whether the symptom actually stayed resolved. On FAIL with
auto_reopen=True the WO is set back to in_progress and an escalation file is
written (consumed by the pulse open-escalations counter). This is the safety
net behind the close gate — a WO can close green and still regress later.

Split out of runner.py (WO-GF-CORE-HEALTH-SKILLS).
"""

from __future__ import annotations

import uuid
from datetime import UTC
from pathlib import Path


def _read_wo_tasks_for_outcome(conn, work_order_id: str) -> list[dict]:
    has_ac = any(
        r[1] == "acceptance_criteria"
        for r in conn.execute("PRAGMA table_info(business_tasks)").fetchall()
    )
    cols = "title, description, status" + (", acceptance_criteria" if has_ac else "")
    rows = conn.execute(
        f"SELECT {cols} FROM business_tasks WHERE work_order_id = ? ORDER BY created_at ASC",
        (work_order_id,),
    ).fetchall()
    return [
        {
            "title": r[0],
            "description": r[1] or "",
            "status": r[2],
            "acceptance_criteria": (r[3] or "") if has_ac else "",
        }
        for r in rows
    ]


def evaluate_wo_outcome(
    work_order_id: str,
    *,
    db_path: Path,
    source_root: Path | None = None,
    symptom_only: bool = False,
) -> dict:
    """Re-run a closed WO's originating_symptom (+ task ACs unless symptom_only).

    Returns ``{work_order_id, title, passed, failures}``. ``passed`` is False when
    the symptom SQL-CHECK still fails or any executable AC fails.
    """
    import sqlite3

    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT title, originating_symptom FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if row is None:
            return {"work_order_id": work_order_id, "passed": True, "failures": [], "skipped": True}
        title, symptom = row
        tasks = [] if symptom_only else _read_wo_tasks_for_outcome(conn, work_order_id)
    finally:
        conn.close()

    failures: list[str] = []

    if symptom:
        from core.work_orders.close import _check_originating_symptom

        reason = _check_originating_symptom(symptom, db_path)
        if reason:
            failures.append(reason)

    if tasks:
        from core.work_orders.verify import resolve_project_root, run_executable_checks

        # Run the WO's checks in ITS target repo (project_path), falling back to the
        # passed source_root then the process cwd — same repo-awareness as the close
        # gate, so a regression is judged against the repo the work actually lives in.
        project_root = resolve_project_root(work_order_id, db_path) or source_root
        ac_results = run_executable_checks(tasks, db_path, project_root=project_root)
        for t_title, checks in ac_results.items():
            for c in checks:
                if not c.get("passed"):
                    failures.append(
                        f"executable_ac[{t_title}]: {c.get('kind', 'CHECK')} "
                        f"{c.get('expr', '')!r} FAILED — {c.get('error') or 'check returned falsy'}"
                    )

    return {
        "work_order_id": work_order_id,
        "title": title,
        "passed": not failures,
        "failures": failures,
    }


def _record_outcome_run(work_order_id: str, outcome: dict, db_path: Path) -> None:
    """Emit the outcome eval as an eval.run.completed canonical event (never raises).

    History for outcome eval runs now lives solely in business_canonical_events
    (T4 dropped ds_eval_runs). emit_eval_run_event is itself fail-open, but the
    never-raises contract here is load-bearing for the close path, so it gets
    its own guard rather than relying on the callee's.
    """
    try:
        from core.eval.events import emit_eval_run_event

        emit_eval_run_event(
            {
                "run_id": str(uuid.uuid4()),
                "eval_id": f"outcome:{work_order_id[:8]}",
                "work_order_id": work_order_id,
                "passed": outcome["passed"],
                "failure_reasons": outcome["failures"],
                "run_mode": "outcome",
            },
            work_order_id=work_order_id,
        )
    except Exception:
        pass


def _reopen_and_escalate(
    work_order_id: str,
    outcome: dict,
    *,
    db_path: Path,
    source_root: Path | None = None,
    dream_studio_home: Path | None = None,
) -> None:
    """Set a regressed WO back to in_progress and write an unresolved escalation file.

    The business_work_orders status write goes through the work-order mutation
    layer (reopen_work_order) — never a direct write from the eval layer — to
    respect the authority boundary (dependency Rule 3). reopen_work_order also
    emits work_order.reopened and syncs the read model.
    """
    from core.work_orders.escalation import (
        escalate_to_operator,
        mark_escalated,
        register_retry,
    )
    from core.work_orders.mutations import reopen_work_order

    _reason = "; ".join(str(f) for f in outcome.get("failures", [])) or "outcome regressed"

    # WO-ESCALATION-LADDER T4: count this retry attempt. When the cap is reached, stop
    # the auto-retry loop and hand the WO to the operator — do NOT silently reopen
    # again. The escalation file below is replaced by an operator-action escalation.
    _retry = register_retry(work_order_id, db_path=Path(db_path))
    if _retry["capped"]:
        escalate_to_operator(
            work_order_id,
            db_path=Path(db_path),
            dream_studio_home=dream_studio_home,
            reason=(
                f"retry cap reached ({_retry['retry_count']}/{_retry['retry_cap']}); "
                f"last failure: {_reason}"
            ),
        )
        return

    reopen_work_order(
        work_order_id=work_order_id,
        reason="outcome_eval: symptom regressed after close",
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )

    # Escalate: the reopened WO carries the Opus capability flag so its retry is
    # routed to a more capable model (WO-ESCALATION-LADDER T2). Both execution
    # surfaces read this via escalation.resolve_executor.
    mark_escalated(work_order_id, db_path=Path(db_path), reason=_reason)

    # Escalation file — counted by the pulse open-escalations scan
    # (meta_dir/*.md containing "ESC-" and "unresolved").
    home = Path(dream_studio_home) if dream_studio_home else Path.home() / ".dream-studio"
    meta_dir = home / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    esc_path = meta_dir / f"ESC-OUTCOME-{work_order_id[:8]}.md"
    reasons = "\n".join(f"- {r}" for r in outcome["failures"])
    esc_path.write_text(
        f"# ESC-OUTCOME-{work_order_id[:8]} — status: unresolved\n\n"
        f"Outcome eval re-opened work order `{work_order_id}` "
        f"({outcome.get('title', '')}). The symptom/ACs regressed after close:\n\n"
        f"{reasons}\n",
        encoding="utf-8",
    )
    # WO-FILESDB-C4B: dual-write to the authority artifact store (kind='escalation',
    # instance_key='outcome'). Disk write above stays during the transition (C4B-3).
    from core.work_orders.escalation import _record_escalation_artifact

    _record_escalation_artifact(
        work_order_id,
        instance_key="outcome",
        reason=_reason,
        db_path=Path(db_path),
    )


def run_outcome_eval(
    *,
    db_path: Path,
    source_root: Path | None = None,
    dream_studio_home: Path | None = None,
    auto_reopen: bool = True,
    symptom_only: bool = False,
    window_hours: float | None = None,
) -> dict:
    """Re-run outcomes for closed WOs that have an originating symptom.

    ``window_hours`` scopes to *recently*-closed WOs (closed_at within the window);
    ``None`` evaluates all closed WOs. The pulse passes a finite window so the
    safety net never auto-reopens ancient WOs whose symptom SQL is environment-
    dependent. On FAIL with ``auto_reopen``: set the WO back to in_progress and
    write an escalation file. Returns ``{ok, evaluated, failed, results}``.
    """
    import sqlite3
    from datetime import datetime, timedelta

    db_path = Path(db_path)
    query = (
        "SELECT work_order_id FROM business_work_orders"
        " WHERE status = 'closed'"
        " AND originating_symptom IS NOT NULL AND TRIM(originating_symptom) <> ''"
    )
    params: tuple = ()
    if window_hours is not None:
        cutoff = (datetime.now(UTC) - timedelta(hours=window_hours)).isoformat()
        # closed_at is ISO-8601 → lexicographic comparison is chronological.
        query += " AND closed_at IS NOT NULL AND closed_at >= ?"
        params = (cutoff,)
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    results: list[dict] = []
    for (wo_id,) in rows:
        outcome = evaluate_wo_outcome(
            wo_id, db_path=db_path, source_root=source_root, symptom_only=symptom_only
        )
        _record_outcome_run(wo_id, outcome, db_path)
        if not outcome["passed"] and auto_reopen:
            try:
                _reopen_and_escalate(
                    wo_id,
                    outcome,
                    db_path=db_path,
                    source_root=source_root,
                    dream_studio_home=dream_studio_home,
                )
                outcome["reopened"] = True
            except Exception as exc:  # pragma: no cover - defensive
                outcome["reopen_error"] = str(exc)
        results.append(outcome)

    return {
        "ok": True,
        "evaluated": len(results),
        "failed": [r for r in results if not r["passed"]],
        "results": results,
    }
