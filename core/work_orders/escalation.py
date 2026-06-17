"""Escalation ladder (WO-ESCALATION-LADDER).

When the DETERMINISTIC verifier/outcome-eval says NOT FIXED, the platform must
not silently re-close. Per AD-8 the deterministic layer owns the escalate
DECISION; the AI owns the retry CONTENT. This module provides the decision half:

  compute_not_fixed_signal(...) — pure predicate over three deterministic inputs:
    AC fail OR symptom persists OR grader high-confidence-not-fixed.
  not_fixed_for_work_order(...) — derives those inputs for a specific WO by
    re-running its outcome (symptom + executable ACs) and folding in an optional
    grader verdict.

Downstream tasks (T2–T5) consume the signal to: route the retry to Opus, require
an independent adversarial review before re-close, and cap retries before
escalating to the operator.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

# A grader "not fixed" verdict only counts when the grader was confident. An
# unreviewable / low-signal grader must NOT by itself trip the ladder (precedent:
# WO-VERIFY-NOSUMMARY — empty grader output is unreviewable, not not-fixed).
GRADER_NOT_FIXED_CONFIDENCE_THRESHOLD = 0.7

# Capability flag: an escalated WO's retry is routed to a more capable model.
ESCALATION_EXECUTOR = "opus"
# Default model when a WO is not escalated.
DEFAULT_EXECUTOR = "sonnet"
# Retry cap before the ladder stops auto-retrying and escalates to the operator.
DEFAULT_RETRY_CAP = 3
RETRY_CAP_CONFIG_KEY = "escalation.retry_cap"
RETRY_CAP_ENV = "DREAM_STUDIO_ESCALATION_RETRY_CAP"


def compute_not_fixed_signal(
    *,
    ac_failed: bool = False,
    symptom_persists: bool = False,
    grader_not_fixed: bool = False,
    grader_confidence: float = 0.0,
) -> dict[str, Any]:
    """Pure deterministic not-fixed predicate.

    Returns ``{"not_fixed": bool, "reasons": [...]}``. ``not_fixed`` is True when
    any deterministic signal fires: a failing executable AC, a persisting
    originating symptom, or a *high-confidence* grader not-fixed verdict.
    """
    reasons: list[str] = []
    if ac_failed:
        reasons.append("ac_fail")
    if symptom_persists:
        reasons.append("symptom_persists")
    if grader_not_fixed and grader_confidence >= GRADER_NOT_FIXED_CONFIDENCE_THRESHOLD:
        reasons.append("grader_high_confidence_not_fixed")
    return {"not_fixed": bool(reasons), "reasons": reasons}


def not_fixed_for_work_order(
    work_order_id: str,
    *,
    db_path: Path,
    source_root: Path | None = None,
    verdict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute the not-fixed signal for a specific WO.

    Re-runs the WO outcome (originating symptom + executable ACs via the outcome
    eval) and folds in an optional independent-review ``verdict``. Returns the
    same shape as ``compute_not_fixed_signal`` plus ``work_order_id``.
    """
    from core.eval.runner import evaluate_wo_outcome

    outcome = evaluate_wo_outcome(work_order_id, db_path=Path(db_path), source_root=source_root)
    failures = outcome.get("failures", [])
    ac_failed = any(str(f).startswith("executable_ac") for f in failures)
    symptom_persists = any("originating_symptom" in str(f) for f in failures)

    grader_not_fixed = False
    grader_confidence = 0.0
    if verdict is not None:
        # A grader that ran and did NOT pass (and is not merely unreviewable) is a
        # not-fixed signal at its reported confidence.
        if not verdict.get("unreviewable") and verdict.get("passed") is False:
            grader_not_fixed = True
            grader_confidence = float(
                verdict.get("confidence", verdict.get("correctness_score", 0.0)) or 0.0
            )

    signal = compute_not_fixed_signal(
        ac_failed=ac_failed,
        symptom_persists=symptom_persists,
        grader_not_fixed=grader_not_fixed,
        grader_confidence=grader_confidence,
    )
    signal["work_order_id"] = work_order_id
    return signal


# ── Escalation state (ds_escalations) ──────────────────────────────────────────
# The deterministic signal above decides WHETHER to escalate; the helpers below
# record the escalation and let both execution paths consume the capability flag.
# ds_escalations is operational SDLC metadata (not business_* state and not an
# event table), so direct sqlite access is correct here — same pattern as
# core/config/authority.py's ds_config helpers.


def read_escalation(work_order_id: str, *, db_path: Path) -> dict[str, Any] | None:
    """Return the escalation row for a WO as a dict, or None if it has none."""
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT work_order_id, escalation_level, retry_count, designated_executor,"
                " last_reason FROM ds_escalations WHERE work_order_id = ?",
                (work_order_id,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    return {
        "work_order_id": row[0],
        "escalation_level": row[1],
        "retry_count": row[2],
        "designated_executor": row[3],
        "last_reason": row[4],
    }


def resolve_executor(work_order_id: str, *, db_path: Path, default: str = DEFAULT_EXECUTOR) -> str:
    """Resolve which model should execute this WO's (re)try.

    An escalated WO carries a ``designated_executor`` capability flag (``opus``);
    everything else gets ``default``. Both the autonomous loop and the manual path
    call this so routing is identical on both surfaces (T5).
    """
    row = read_escalation(work_order_id, db_path=db_path)
    if row and row.get("designated_executor"):
        return str(row["designated_executor"])
    return default


def mark_escalated(
    work_order_id: str,
    *,
    db_path: Path,
    reason: str = "",
    executor: str = ESCALATION_EXECUTOR,
) -> dict[str, Any]:
    """Record an escalation for a WO: bump escalation_level and set the capability
    flag routing its retry to ``executor`` (Opus by default).

    Idempotent upsert keyed by work_order_id. Returns the resulting escalation row.
    """
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO ds_escalations"
            " (work_order_id, escalation_level, retry_count, designated_executor,"
            "  last_reason, created_at, updated_at)"
            " VALUES (?, 1, 0, ?, ?, datetime('now'), datetime('now'))"
            " ON CONFLICT(work_order_id) DO UPDATE SET"
            "   escalation_level = escalation_level + 1,"
            "   designated_executor = excluded.designated_executor,"
            "   last_reason = excluded.last_reason,"
            "   updated_at = datetime('now')",
            (work_order_id, executor, reason),
        )
    row = read_escalation(work_order_id, db_path=db_path)
    if row is None:
        # read_escalation swallows sqlite errors and returns None; surface a real
        # error instead of an AssertionError so callers see a graceful failure
        # (WO-GATE-HARDEN-CLEANUP). The row was just upserted, so this is only
        # reachable if the DB became unreadable between write and re-read.
        raise RuntimeError(
            f"mark_escalated: escalation row not readable after upsert for {work_order_id}"
        )
    return row


def get_retry_cap(*, db_path: Path) -> int:
    """Resolve the retry cap: env var > ds_config row > built-in default (3)."""
    env = os.environ.get(RETRY_CAP_ENV)
    if env:
        try:
            return int(env)
        except ValueError:
            pass
    try:
        from core.config.authority import get_config_value

        raw = get_config_value(RETRY_CAP_CONFIG_KEY, db_path)
        if raw is not None:
            return int(raw)
    except Exception:
        pass
    return DEFAULT_RETRY_CAP


def register_retry(work_order_id: str, *, db_path: Path) -> dict[str, Any]:
    """Increment the retry counter for an escalated WO and report whether the cap
    is reached.

    Returns ``{work_order_id, retry_count, retry_cap, capped}``. When ``capped`` is
    True the caller must STOP auto-retrying and escalate to the operator — no silent
    retry loop (T4).
    """
    cap = get_retry_cap(db_path=db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO ds_escalations"
            " (work_order_id, escalation_level, retry_count, created_at, updated_at)"
            " VALUES (?, 0, 1, datetime('now'), datetime('now'))"
            " ON CONFLICT(work_order_id) DO UPDATE SET"
            "   retry_count = retry_count + 1,"
            "   updated_at = datetime('now')",
            (work_order_id,),
        )
        retry_count = conn.execute(
            "SELECT retry_count FROM ds_escalations WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()[0]
    return {
        "work_order_id": work_order_id,
        "retry_count": retry_count,
        "retry_cap": cap,
        "capped": retry_count >= cap,
    }


def escalate_to_operator(
    work_order_id: str,
    *,
    db_path: Path,
    reason: str = "",
    dream_studio_home: Path | None = None,
) -> Path:
    """Hand a WO back to the operator when the retry cap is reached — no silent loop.

    Writes an unresolved operator escalation file (counted by the pulse
    open-escalations scan, which looks for ``ESC-`` + ``unresolved``). Returns the
    file path. Does NOT reopen the WO: the ladder stops auto-retrying here and waits
    for the operator.
    """
    home = Path(dream_studio_home) if dream_studio_home else Path.home() / ".dream-studio"
    meta_dir = home / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    esc_path = meta_dir / f"ESC-RETRYCAP-{work_order_id[:8]}.md"
    esc_path.write_text(
        f"# ESC-RETRYCAP-{work_order_id[:8]} — status: unresolved\n\n"
        f"Work order `{work_order_id}` hit the escalation retry cap and now requires "
        f"OPERATOR intervention — the ladder has stopped auto-retrying (no silent loop).\n\n"
        f"Reason: {reason or 'retry cap reached'}\n",
        encoding="utf-8",
    )
    return esc_path
