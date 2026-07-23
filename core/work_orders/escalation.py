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
import re
import sqlite3
from datetime import datetime, UTC
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
    _record_escalation_artifact(
        work_order_id,
        instance_key="retrycap",
        reason=reason or "retry cap reached",
        db_path=db_path,
    )
    return esc_path


def _record_escalation_artifact(
    work_order_id: str,
    *,
    instance_key: str,
    reason: str,
    db_path: Path,
) -> None:
    """WO-FILESDB-C4B: dual-write the escalation to the authority artifact store
    (business_work_order_artifacts kind='escalation'). The disk ESC-*.md write stays
    during the transition until the pulse scan reads the store (C4B-3). Best-effort and
    fully isolated — never affects the escalation ladder's primary behavior."""
    try:
        import json as _json

        from core.work_orders.artifacts import set_wo_artifact

        set_wo_artifact(
            work_order_id,
            "escalation",
            _json.dumps(
                {
                    "type": instance_key,
                    "status": "unresolved",
                    "reason": reason,
                    "work_order_id": work_order_id,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ),
            instance_key=instance_key,
            db_path=db_path,
        )
    except Exception:
        pass


# ── Operator escalation surface (business_work_order_artifacts kind='escalation') ──
# The helpers below read/resolve the operator-facing escalation ARTIFACTS written by
# _record_escalation_artifact — distinct from the ds_escalations ladder table above
# (which carries the retry/executor routing state). These back the `ds escalation`
# command (WO-FILESDB-C4B S2) so the operator can list open escalations and mark them
# resolved from the authority instead of hand-editing loose ESC-*.md disk files. Store
# writes are additive: the pulse open-escalation count keeps reading disk until C4B-3
# repoints it at this store, at which point a 'resolved' status drops out of the count.


def _parse_escalation_artifact(
    work_order_id: str, instance_key: str, content: str, updated_at: str = ""
) -> dict[str, Any]:
    """Normalize a stored escalation artifact JSON into a stable dict.

    Tolerates malformed / empty content (returns 'unknown' status) so a single bad
    row never breaks a list query.
    """
    import json

    try:
        data = json.loads(content) if content else {}
    except (ValueError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "work_order_id": data.get("work_order_id") or work_order_id,
        "type": data.get("type") or instance_key,
        "status": data.get("status") or "unknown",
        "reason": data.get("reason", ""),
        "created_at": data.get("created_at", ""),
        "resolved_at": data.get("resolved_at"),
        "updated_at": updated_at,
    }


def list_escalations(
    *, db_path: Path | None = None, include_resolved: bool = False
) -> list[dict[str, Any]]:
    """List operator escalation artifacts across all work orders.

    Defaults to only ``unresolved`` escalations — the operator-actionable set.
    Pass ``include_resolved=True`` to see the full history. Most-recent first.
    """
    from core.work_orders.artifacts import list_artifacts_by_kind

    out: list[dict[str, Any]] = []
    for wo_id, instance_key, content, updated_at in list_artifacts_by_kind(
        "escalation", db_path=db_path
    ):
        rec = _parse_escalation_artifact(wo_id, instance_key, content, updated_at)
        if not include_resolved and rec["status"] != "unresolved":
            continue
        out.append(rec)
    return out


def get_escalations(work_order_id: str, *, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Return every escalation artifact for one WO (retrycap + outcome instances)."""
    from core.work_orders.artifacts import list_wo_artifacts

    return [
        _parse_escalation_artifact(work_order_id, instance_key, content)
        for instance_key, content in list_wo_artifacts(work_order_id, "escalation", db_path=db_path)
    ]


def resolve_escalation(
    work_order_id: str,
    *,
    db_path: Path | None = None,
    instance_key: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Mark a WO's escalation artifact(s) resolved (status → 'resolved', + resolved_at).

    When ``instance_key`` is None every escalation instance for the WO is resolved
    (both ``retrycap`` and ``outcome``); pass an ``instance_key`` to resolve just one.
    Idempotent — an already-resolved instance is reported but not rewritten. Returns
    ``{work_order_id, resolved: [type...], already_resolved: [type...], found: bool}``.
    """
    import json

    from core.work_orders.artifacts import list_wo_artifacts, set_wo_artifact

    rows = list_wo_artifacts(work_order_id, "escalation", db_path=db_path)
    if instance_key is not None:
        rows = [(ik, content) for ik, content in rows if ik == instance_key]

    resolved: list[str] = []
    already_resolved: list[str] = []
    now = datetime.now(UTC).isoformat()
    for ik, content in rows:
        try:
            data = json.loads(content) if content else {}
        except (ValueError, TypeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        if data.get("status") == "resolved":
            already_resolved.append(data.get("type") or ik)
            continue
        data["status"] = "resolved"
        data["resolved_at"] = now
        if note:
            data["resolution_note"] = note
        set_wo_artifact(
            work_order_id, "escalation", json.dumps(data), instance_key=ik, db_path=db_path
        )
        resolved.append(data.get("type") or ik)

    return {
        "work_order_id": work_order_id,
        "resolved": resolved,
        "already_resolved": already_resolved,
        "found": bool(rows),
    }


# ── Legacy disk ESC-*.md → store migration (WO-FILESDB-C4B S3) ──────────────────
# During the transition the pulse's open-escalation count moves from a disk glob
# (meta/*.md containing "ESC-" + "unresolved") to the authority store. The scan +
# backfill below let the pulse read the store while guaranteeing the count never
# drops: any open disk ESC file that predates the S1 dual-write is migrated in first.
# S5 drops the disk writes; then scan_open_escalation_files simply finds nothing.

# Disk ESC files are named ESC-<TYPE>-<wo8>.md (see escalate_to_operator /
# runner_outcome ESC-OUTCOME), e.g. ESC-RETRYCAP-1a2b3c4d.
_ESC_FILENAME_RE = re.compile(r"^ESC-([A-Za-z]+)-([0-9a-fA-F]{6,})$")
_ESC_REASON_RE = re.compile(r"^Reason:\s*(.+)$", re.MULTILINE)


def scan_open_escalation_files(meta_dir: Path | str | None) -> list[Path]:
    """Return the meta-dir ESC-*.md files still marked unresolved (legacy disk scan).

    This is the exact predicate the pulse used before C4B-3 ("ESC-" + "unresolved");
    factored out so the store-backed scan can migrate + fall back to it.
    """
    if not meta_dir:
        return []
    directory = Path(meta_dir)
    if not directory.is_dir():
        return []
    out: list[Path] = []
    for candidate in sorted(directory.glob("*.md")):
        try:
            text = candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "ESC-" in text and "unresolved" in text.lower():
            out.append(candidate)
    return out


def _resolve_wo_by_prefix(wo_prefix: str, db_path: Path) -> str | None:
    """Resolve a full work_order_id from the 8-char prefix in an ESC filename.

    Returns None when there is no match or the prefix is ambiguous (>1 match) —
    backfill then skips that file rather than guess.
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        rows = conn.execute(
            "SELECT work_order_id FROM business_work_orders WHERE work_order_id LIKE ? LIMIT 2",
            (wo_prefix + "%",),
        ).fetchall()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    return rows[0][0] if len(rows) == 1 else None


def backfill_open_escalations_from_disk(meta_dir: Path | str | None, *, db_path: Path) -> int:
    """Migrate open disk ESC-*.md files into the authority escalation store (idempotent).

    For each unresolved disk ESC file, resolve its work order + instance_key from the
    filename and — unless an escalation artifact already exists for that (wo, type) —
    record one (status='unresolved'). Returns the number newly written. Best-effort:
    unparseable names, unknown/ambiguous WOs, and store-write failures are skipped, and
    an already-migrated escalation is never duplicated (the store's unique key holds).
    """
    from core.work_orders.artifacts import get_wo_artifact

    written = 0
    for esc_file in scan_open_escalation_files(meta_dir):
        match = _ESC_FILENAME_RE.match(esc_file.stem)
        if not match:
            continue
        raw_type = match.group(1).lower()
        wo_prefix = match.group(2).lower()
        if "retrycap" in raw_type:
            instance_key = "retrycap"
        elif "outcome" in raw_type:
            instance_key = "outcome"
        else:
            instance_key = raw_type
        work_order_id = _resolve_wo_by_prefix(wo_prefix, db_path)
        if not work_order_id:
            continue
        if (
            get_wo_artifact(work_order_id, "escalation", instance_key=instance_key, db_path=db_path)
            is not None
        ):
            continue  # already represented in the store
        try:
            reason_match = _ESC_REASON_RE.search(
                esc_file.read_text(encoding="utf-8", errors="ignore")
            )
        except OSError:
            reason_match = None
        reason = reason_match.group(1).strip() if reason_match else "migrated from disk ESC file"
        _record_escalation_artifact(
            work_order_id, instance_key=instance_key, reason=reason, db_path=db_path
        )
        written += 1
    return written
