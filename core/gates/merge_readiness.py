"""Is this work order's own review verdict green? (WO-MERGE-BEFORE-VERIFY)

Every red on ``main`` on 2026-08-19 was one failing test out of ~5,386, from a work
order whose own ``ds work-order verify`` was failing or had never run at the moment
its PR was merged:

  16:39-18:47 — four consecutive reds, ``test_grader_contract_schema[falsification]``
  21:12       — two reds, ``test_doctor_fix_calls_install_when_skills_missing``

Both were merged past a known-bad or absent verdict. The verdict for 9a9e23da is on
record as FAILED, naming two gaps, and its PR merged anyway.

THE GAP THIS CLOSES. Verify is a CLOSE gate, and merge happens BEFORE close. So the
whole apparatus — five grader roles, the falsification analyst, provenance-bound
verdicts, the ``independent_review`` gate — cannot influence the one decision that
puts code on ``main``. Merge authorization is ``gh pr checks --watch`` over the
3-platform ``pr-smoke`` matrix, which runs 11 focused files; a work order's own
verdict is not consulted at all.

That is the same shape as the complaint that opened this milestone: a gate that
exists, is correct, and sits where it cannot stop the thing it was built to stop.

WHAT THIS IS NOT. It does not block merges, and it must not: an urgent hotfix has
to be mergeable, and a red verdict on someone else's work order must never stop
unrelated work. It reads the verdict and reports it, and merging past a bad one is
recorded as a bypass rather than passing unremarked. Invisibility was the defect,
not permissiveness — the same conclusion WO-MAINRED-VISIBILITY reached about a red
``main``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# A branch may point at its work order as `wo-<shortid>` or carry the full uuid.
_BRANCH_WO = re.compile(r"wo-([0-9a-f]{8,})", re.IGNORECASE)
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def resolve_work_order(
    *, work_order_id: str | None = None, branch: str | None = None, db_path: Path | None = None
) -> tuple[str | None, str | None]:
    """Resolve a work order id from an explicit id or a branch name.

    Returns ``(work_order_id, reason_if_unresolved)``. Never guesses: a branch that
    names no work order resolves to None WITH a reason, because "this branch has no
    WO" and "this WO has no verdict" are different facts with different remedies,
    and collapsing them would make the report unactionable.
    """
    if work_order_id:
        return work_order_id, None
    if not branch:
        return None, "no work order id and no branch given"

    candidates: list[str] = []
    full = _UUID.search(branch)
    if full:
        candidates.append(full.group(0))
    short = _BRANCH_WO.search(branch)
    if short:
        candidates.append(short.group(1))
    if not candidates:
        return None, f"branch {branch!r} does not name a work order (no uuid, no wo-<shortid>)"
    if db_path is None:
        return None, "no authority database available to resolve the work order"

    import sqlite3

    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.Error as exc:
        return None, f"authority unavailable: {exc}"
    try:
        for candidate in candidates:
            row = conn.execute(
                "SELECT work_order_id FROM business_work_orders WHERE work_order_id LIKE ?",
                (candidate + "%",),
            ).fetchone()
            if row:
                return row[0], None
    except sqlite3.Error as exc:
        return None, f"authority query failed: {exc}"
    finally:
        conn.close()
    return None, f"no work order matches {candidates[0]!r}"


def verdict_state(
    work_order_id: str, *, db_path: Path | None = None, planning_root: Path | None = None
) -> dict[str, Any]:
    """The work order's stored review verdict, classified for a merge decision.

    ``state`` is one of:

    - ``passed``       — verify certified the work
    - ``failed``       — verify found real gaps; the summary says what
    - ``unreviewable`` — verify ran but could not judge (grader outage, no evidence).
      NOT the same as failed: nothing was found wrong, nothing was confirmed right.
    - ``absent``       — verify never ran, or its artifact carries no provenance
    - ``unreadable``   — an artifact exists but cannot be parsed

    ``unreviewable`` and ``absent`` are kept apart deliberately. One means "we tried
    and could not tell", the other "we never tried", and the remedies differ: retry
    versus run it at all. The 2026-08-19 merges were mostly the second.
    """
    result: dict[str, Any] = {
        "work_order_id": work_order_id,
        "state": "absent",
        "summary": None,
        "reason": None,
        "generator": None,
    }
    # BOTH STORES, via the reader the close gate already uses. The first cut called
    # get_wo_artifact_envelope directly — authority only — so a verdict that landed
    # on the disk fallback read as "absent". Caught by the very first smoke test
    # against real data: 6a4c21d1 had a FAILING verdict on disk and this reported
    # "verify has not run", which are opposite remedies (fix the gaps vs run it at
    # all). Reusing _artifact_with_envelope means there is one reader for one
    # artifact rather than a second implementation that can disagree — the same
    # single-source argument as the grader-payload normaliser and the envelope rule.
    try:
        from core.work_orders.close_shared import _artifact_with_envelope

        wo_dir = (planning_root or Path.cwd() / ".planning") / "work-orders" / work_order_id
        raw, envelope = _artifact_with_envelope(work_order_id, wo_dir, "review_verdict", db_path)
    except Exception as exc:  # noqa: BLE001 - a reader must not raise into a merge check
        result["reason"] = f"verdict unreadable: {type(exc).__name__}: {exc}"[:200]
        result["state"] = "unreadable"
        return result

    if raw is None:
        result["reason"] = "no review verdict stored — verify has not run for this work order"
        return result
    if not envelope or not envelope.get("generator"):
        # Same rule the independent_review gate applies: an envelope-less verdict is
        # hand-written or pre-provenance, and either way is not a certified review.
        result["reason"] = "stored verdict carries no provenance envelope (hand-written or legacy)"
        return result
    result["generator"] = envelope.get("generator")

    try:
        verdict = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        result["state"] = "unreadable"
        result["reason"] = f"stored verdict is not valid JSON: {exc}"[:200]
        return result
    if not isinstance(verdict, dict):
        result["state"] = "unreadable"
        result["reason"] = "stored verdict is not a JSON object"
        return result

    from core.work_orders.close_shared import verdict_evidence

    summary, findings = verdict_evidence(verdict)
    result["summary"] = summary or None
    # STRUCTURED SIGNAL, NOT A KEYWORD IN PROSE. The first cut asked whether
    # "unreviewable" appeared ANYWHERE in the summary — and a real verdict whose
    # prose read "it separates never-run from failed from unreviewable" was
    # therefore classified unreviewable, despite carrying three concrete gaps and a
    # 0.793 composite. Classifying a judgement by a word inside it is how a real
    # failure gets softened into "we could not tell", which is the inversion this
    # module is supposed to prevent.
    #
    # verify marks an unjudgeable run two ways, both checkable without reading
    # prose: an `unreviewable` key, and a summary that OPENS with its own warning
    # phrase. A prefix, not a substring.
    if verdict.get("unreviewable") or summary.lower().startswith("independent review unreviewable"):
        result["state"] = "unreviewable"
        result["reason"] = summary or "verify could not judge the work"
        return result
    if verdict.get("passed") is True:
        result["state"] = "passed"
        return result

    reasons = findings
    if not summary and not reasons:
        # WO-VERDICT-PARTIAL-WRITE's lesson: an empty record is not a judgement.
        result["state"] = "unreviewable"
        result["reason"] = "verdict says passed=False but carries no summary and no reasons"
        return result
    result["state"] = "failed"
    result["reason"] = summary or "; ".join(str(r) for r in reasons)[:300]
    return result


def merge_readiness(
    *,
    work_order_id: str | None = None,
    branch: str | None = None,
    db_path: Path | None = None,
    planning_root: Path | None = None,
) -> dict[str, Any]:
    """Report whether this change's work order has a green verdict.

    ``{"ready": bool, "state": ..., "work_order_id": ..., "reason": ...,
       "advice": ...}``

    ``ready`` is False for anything other than ``passed`` — including
    ``unreviewable``, because "we could not tell" is not "it is fine". It is a
    REPORT: nothing here blocks a merge. A branch with no work order is
    ``ready=True`` with a note, since plenty of legitimate changes (a docs typo, a
    revert) have no WO and refusing those would make the check something people
    route around.
    """
    resolved, why = resolve_work_order(work_order_id=work_order_id, branch=branch, db_path=db_path)
    if resolved is None:
        return {
            "ready": True,
            "state": "no_work_order",
            "work_order_id": None,
            "reason": why,
            "advice": (
                "No work order is associated with this change, so there is no verdict"
                " to consult. Merge on the 3-platform matrix as usual."
            ),
        }

    info = verdict_state(resolved, db_path=db_path, planning_root=planning_root)
    state = info["state"]
    ready = state == "passed"
    advice = {
        "passed": "Verify certified this work order. Merge on a green 3-platform matrix.",
        "failed": (
            "Verify found gaps in THIS work order. Fix them, or record the override"
            " deliberately — every red on main on 2026-08-19 came from merging past"
            " a verdict like this one."
        ),
        "unreviewable": (
            "Verify ran but could not judge (grader outage or no located evidence)."
            " Nothing was found wrong and nothing was confirmed right — re-run verify"
            " rather than reading this as approval."
        ),
        "absent": (
            "Verify has never produced a provenance-bound verdict for this work"
            " order. Run: py -m interfaces.cli.ds work-order verify <id>"
        ),
        "unreadable": "The stored verdict cannot be parsed. Re-run verify.",
    }.get(state, "Unknown verdict state — treat as not ready.")
    return {
        "ready": ready,
        "state": state,
        "work_order_id": resolved,
        "reason": info.get("reason"),
        "summary": info.get("summary"),
        "advice": advice,
    }


def record_merge_override(
    *,
    work_order_id: str | None,
    state: str,
    reason: str,
    pull_request: int | None = None,
    merge_commit: str | None = None,
) -> None:
    """Record a merge made past a non-green verdict as a queryable bypass.

    Uses the existing ``gate.bypassed`` family so ``bypass_report`` and
    ``ds doctor``'s bypass audit already aggregate it — a new event type nobody
    reads would be the invisibility this closes, wearing a different name.
    """
    from core.gates.bypass_event import record_gate_bypass

    record_gate_bypass(
        gate="merge_before_verify",
        reason=reason,
        extra={
            "work_order_id": work_order_id,
            "verdict_state": state,
            "pull_request": pull_request,
            "merge_commit": merge_commit,
        },
    )
