"""Verdict persistence for work-order verify.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the
eval-run persistence (business_work_orders columns + work_order.verified
canonical event) and the DB-first review-verdict persistence (authority
artifact, disk fallback). No logic changes — extracted verbatim from the
original module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ── Verdict persistence ─────────────────────────────────────────────────────────


def _write_eval_run(
    conn: Any,
    *,
    work_order_id: str,
    scores: dict[str, float],
    passed: bool,
    failure_reasons: list[str],
    started_at: str,
    completed_at: str,
    status: str | None = None,
) -> None:
    """Persist the verify verdict: business_work_orders columns and the
    work_order.verified canonical event (via spool). The canonical event is
    the sole durable record of the verify run (T4 dropped ds_eval_runs;
    history is available via business_canonical_events)."""
    verify_status = status or ("passed" if passed else "failed")

    try:
        conn.execute(
            "UPDATE business_work_orders"
            " SET verify_status = ?, verify_score = ?, verified_at = ?"
            " WHERE work_order_id = ?",
            (verify_status, scores["composite_score"], completed_at, work_order_id),
        )
    except Exception:
        # Pre-migration-134 databases lack the columns; non-fatal.
        pass

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        envelope = CanonicalEventEnvelope(
            event_type="work_order.verified",
            session_id=None,
            payload={
                "work_order_id": work_order_id,
                "verify_status": verify_status,
                "completion_score": scores["completion_score"],
                "correctness_score": scores["correctness_score"],
                "quality_score": scores.get("quality_score"),
                "composite_score": scores["composite_score"],
                "passed": passed,
                "failure_reasons": failure_reasons,
                "started_at": started_at,
                "completed_at": completed_at,
            },
            timestamp=completed_at,
            severity="info",
            trace={
                "domain": "sdlc",
                "work_order_id": work_order_id,
                "attribution_status": "fully_attributed",
            },
        )
        _spool_writer.write_event(envelope.to_dict())
    except Exception:
        pass


# ── Review-verdict persistence (WO-FILESDB-C2) ───────────────────────────────────


def _persist_review_verdict(
    work_order_id: str,
    verdict: dict[str, Any],
    *,
    planning_root: Path,
    db_path: Path | None = None,
) -> Path | None:
    """DB-first review-verdict persistence (WO-FILESDB-C2).

    Store the verdict in the authority (``business_work_order_artifacts``,
    kind=``review_verdict``); write ``.planning/work-orders/<id>/review-verdict.json``
    only as a fallback when the artifact table is absent (migration unreleased on the
    live DB during the transition — C6 removes the fallback after release). Returns the
    disk Path when the fallback was used, else None (stored in the authority). The
    close ``independent_review`` gate reads the verdict DB-or-disk.
    """
    from core.work_orders.artifacts import set_wo_artifact

    payload = json.dumps(verdict, indent=2)
    if set_wo_artifact(work_order_id, "review_verdict", payload, db_path=db_path):
        return None
    verdict_dir = planning_root / "work-orders" / work_order_id
    verdict_dir.mkdir(parents=True, exist_ok=True)
    verdict_path = verdict_dir / "review-verdict.json"
    verdict_path.write_text(payload, encoding="utf-8")
    return verdict_path
