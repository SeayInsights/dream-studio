"""Verdict persistence for work-order verify.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the
eval-run persistence (business_work_orders columns + work_order.verified
canonical event) and the DB-first review-verdict persistence (authority
artifact, disk fallback). No logic changes — extracted verbatim from the
original module.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` so readers see all of it or none of it.

    WO-VERDICT-PARTIAL-WRITE. A plain ``write_text`` interrupted mid-flush leaves
    whatever reached disk, and for a review verdict that is worse than leaving
    nothing: an absent verdict is recoverable (re-run verify) while a truncated one
    reads as ``passed: False`` with no summary and BLOCKS a close on work that
    actually passed. Observed live — a killed verify left exactly that artifact and
    the next close reported "independent review: review failed — no summary."

    Same-directory temp file plus ``os.replace``, which is atomic on POSIX and on
    Windows for same-volume renames. The temp file is removed if anything fails, so
    an interrupted write leaves neither a partial verdict nor a stray file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())  # the rename is atomic; the CONTENT must be durable first
        os.replace(tmp_name, str(path))
    except BaseException:
        # BaseException, not Exception: a KeyboardInterrupt mid-write is the exact
        # scenario this exists for, and it must not leave the temp file behind.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


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
    truncated: str | None = None,
    verified_at: str | None = None,
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

    # PARTIAL ANALYSIS AND PAIRING (falsification analyst findings on the verify
    # flow): the truncation caveat used to live only in the verdict, so close and
    # ds project state reported UNVERIFIED items from a PARTIAL enumeration
    # without knowing it was partial; and a crash between this write and the
    # verdict write could pair run N's ledger with run N-1's verdict undetectably.
    # Carrying both the caveat and the run's verified_at makes a partial ledger
    # self-describing and a mismatched pair detectable.
    _payload: dict[str, Any] = {
        "work_order_id": work_order_id,
        "unverified": unverified,
        "count": len(unverified),
    }
    if truncated:
        _payload["truncated"] = truncated
    if verified_at:
        _payload["verified_at"] = verified_at
    payload = json.dumps(_payload, indent=2)
    ledger_path = planning_root / "work-orders" / work_order_id / _UNVERIFIED_LEDGER_FILENAME
    if set_wo_artifact(
        work_order_id,
        "report",
        payload,
        instance_key="unverified_risks",
        db_path=db_path,
        generator="ds work-order verify (falsification analyst)",
        project_root=project_root,
    ):
        # SINGLE SOURCE OF TRUTH (quality rule 7, caught by this stage's own verify):
        # a WO whose earlier run fell back to disk and whose later run reached the
        # authority would leave TWO ledgers, and an authority-first reader could
        # serve the older one — version skew between stores on durable state a read
        # path trusts. On a successful authority write, drop any stale disk copy so
        # exactly one ledger exists per WO.
        if ledger_path.is_file():
            try:
                ledger_path.unlink()
            except OSError:
                pass  # a stale copy that cannot be removed is still shadowed by the authority
        return None
    # Atomic (WO-VERDICT-PARTIAL-WRITE): a half-written residual-risk ledger
    # would read as a shorter list of risks, which is the silence this stage
    # exists to remove.
    _atomic_write(ledger_path, payload)
    return ledger_path


def read_unverified_ledger(
    work_order_id: str, *, planning_root: Path, db_path: Path | None = None
) -> dict[str, Any] | None:
    """Read a WO's UNVERIFIED ledger — authority first, disk fallback.

    Returns the parsed ledger dict, or None when no analysis ever wrote one
    (distinct from an EMPTY ledger, which means the analyst found no untestable
    residual). Used by close to surface residual risk at declare-done time.

    A ledger that EXISTS but cannot be parsed returns
    ``{"unreadable": <reason>, "unverified": []}`` rather than None: "corrupt"
    and "absent" are different facts, and collapsing them would let a broken
    ledger read as "no residual risk" — the silence this stage exists to remove.
    """
    from core.work_orders.artifacts import get_wo_artifact_envelope

    disk = planning_root / "work-orders" / work_order_id / _UNVERIFIED_LEDGER_FILENAME
    raw, envelope = get_wo_artifact_envelope(
        work_order_id, "report", instance_key="unverified_risks", db_path=db_path
    )
    source = "authority"

    # NEWEST WINS, not authority-first (falsification analyst finding, version_skew
    # on this very function): a run whose authority write LANDED followed by a run
    # whose write NO-OPPED under verify's own transaction lock (the documented
    # fd981a32 case) leaves a newer ledger on disk behind an older one in the
    # authority. An authority-first reader serves the stale copy — the exact
    # skew-on-trusted-durable-state class rule 7 exists to catch. Compare the
    # authority envelope's created_at against the disk file's mtime and take the
    # newer; a missing timestamp on either side loses to a known one.
    if raw is not None and disk.is_file():
        from datetime import UTC, datetime

        authority_at: datetime | None = None
        created = (envelope or {}).get("created_at")
        if created:
            try:
                authority_at = datetime.fromisoformat(str(created))
                if authority_at.tzinfo is None:
                    authority_at = authority_at.replace(tzinfo=UTC)
            except ValueError:
                authority_at = None
        try:
            disk_at: datetime | None = datetime.fromtimestamp(disk.stat().st_mtime, tz=UTC)
        except OSError:
            disk_at = None
        if disk_at is not None and (authority_at is None or disk_at > authority_at):
            raw, source = None, "disk"  # fall through to the disk read below

    if raw is None:
        if not disk.is_file():
            return None
        source = "disk"
        try:
            raw = disk.read_text(encoding="utf-8")
        except OSError as exc:
            return {"unreadable": f"{source} ledger unreadable: {exc}", "unverified": []}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        return {"unreadable": f"{source} ledger is not valid JSON: {exc}", "unverified": []}
    if not isinstance(parsed, dict):
        return {"unreadable": f"{source} ledger is not a JSON object", "unverified": []}
    return parsed


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
    verdict_path = planning_root / "work-orders" / work_order_id / "review-verdict.json"
    _atomic_write(verdict_path, wrapped)
    return verdict_path
