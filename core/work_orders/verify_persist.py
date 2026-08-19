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


_UNVERIFIED_LEDGER_FILENAME = "unverified-risks.json"


def _persist_unverified_ledger(
    work_order_id: str,
    unverified: list[dict[str, Any]],
    *,
    planning_root: Path,
    db_path: Path | None = None,
    project_root: Path | None = None,
) -> Path | None:
    """Persist the UNVERIFIED risk ledger for a WO (WO-FALSIFY-FIRST-PASS).

    Worst-case scenarios the falsification analyst says cannot be tested yet are
    recorded as durable state — named residual risk, surfaced at close — rather
    than left as an unknown. Stored under the existing multi-instance ``report``
    kind (instance_key=``unverified_risks``), so no new artifact kind and no
    migration are needed.

    Returns the disk Path when the authority write did not land, else None
    (stored in the authority) — the same dual-path contract the review verdict
    uses. The fallback matters here for a known reason: this call runs INSIDE
    verify's open authority transaction, so the second connection
    ``set_wo_artifact`` opens can hit a write lock and no-op (registered defect
    WO-ARTIFACT-LOCK-FALLBACK / fd981a32, which makes it authority-native).
    Until then the ledger must survive either way — a residual risk that silently
    fails to persist is exactly the silence this stage exists to remove.

    An EMPTY ledger is written too: "the analyst found no untestable residual"
    and "no analysis ran" must not look identical downstream.
    """
    from core.work_orders.artifacts import set_wo_artifact

    payload = json.dumps(
        {"work_order_id": work_order_id, "unverified": unverified, "count": len(unverified)},
        indent=2,
    )
    if set_wo_artifact(
        work_order_id,
        "report",
        payload,
        instance_key="unverified_risks",
        db_path=db_path,
        generator="ds work-order verify (falsification analyst)",
        project_root=project_root,
    ):
        return None
    ledger_dir = planning_root / "work-orders" / work_order_id
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = ledger_dir / _UNVERIFIED_LEDGER_FILENAME
    ledger_path.write_text(payload, encoding="utf-8")
    return ledger_path


def read_unverified_ledger(
    work_order_id: str, *, planning_root: Path, db_path: Path | None = None
) -> dict[str, Any] | None:
    """Read a WO's UNVERIFIED ledger — authority first, disk fallback.

    Returns the parsed ledger dict, or None when no analysis ever wrote one
    (distinct from an EMPTY ledger, which means the analyst found no untestable
    residual). Used by close to surface residual risk at declare-done time.
    """
    from core.work_orders.artifacts import get_wo_artifact

    raw = get_wo_artifact(work_order_id, "report", instance_key="unverified_risks", db_path=db_path)
    if raw is None:
        disk = planning_root / "work-orders" / work_order_id / _UNVERIFIED_LEDGER_FILENAME
        if not disk.is_file():
            return None
        raw = disk.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _persist_review_verdict(
    work_order_id: str,
    verdict: dict[str, Any],
    *,
    planning_root: Path,
    db_path: Path | None = None,
    project_root: Path | None = None,
    generator: str = "ds work-order verify",
) -> Path | None:
    """DB-first review-verdict persistence (WO-FILESDB-C2).

    Store the verdict in the authority (``business_work_order_artifacts``,
    kind=``review_verdict``); write ``.planning/work-orders/<id>/review-verdict.json``
    only as a fallback when the artifact table is absent (migration unreleased on the
    live DB during the transition — C6 removes the fallback after release). Returns the
    disk Path when the fallback was used, else None (stored in the authority). The
    close ``independent_review`` gate reads the verdict DB-or-disk.

    WO-VERIFY-PROVENANCE: the stored verdict carries a provenance envelope
    (generator identity + the HEAD commit of ``project_root`` at write time) on
    both the authority and disk-fallback paths, so the independent_review gate
    can reject hand-written and stale verdicts.
    """
    from core.work_orders.artifact_envelope import git_head_sha, wrap
    from core.work_orders.artifacts import set_wo_artifact

    payload = json.dumps(verdict, indent=2)
    wrapped = wrap(payload, generator=generator, head_commit_sha=git_head_sha(project_root))
    if set_wo_artifact(work_order_id, "review_verdict", wrapped, db_path=db_path):
        return None
    verdict_dir = planning_root / "work-orders" / work_order_id
    verdict_dir.mkdir(parents=True, exist_ok=True)
    verdict_path = verdict_dir / "review-verdict.json"
    verdict_path.write_text(wrapped, encoding="utf-8")
    return verdict_path
