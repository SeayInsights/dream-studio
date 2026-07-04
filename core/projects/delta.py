"""Baseline→delta computation for brownfield security scans.

Layered matching approach:
  1. Exact hash match (bulk, free) — same rule + file + normalized code excerpt
  2. Previously-adjudicated links (LLM verdicts from prior runs, free)
  3. Pre-pairing residuals by (rule_id, file_path, line proximity) → candidate pairs
  4. LLM adjudicates only plausible pairs; verdict persisted (decided once)
  5. Unpaired orphans = genuinely new or genuinely fixed — no LLM

This design ensures:
- Reformatting (whitespace) → no churn (normalized hash absorbs it)
- Genuine fix → correctly detected as fixed
- Edit-flagged code → LLM says "same issue, persisting" (not churn)
- Multiplicity (fix one of two) → correct pairing, no mis-match

Case 4 (edit-flagged) and Case 5 (multiplicity) are the hard ones.
Case 4 proves LLM adjudication; Case 5 proves pre-pairing precision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ScanDelta:
    """Result of comparing two consecutive security scans."""

    curr_scan_id: str
    prev_scan_id: str
    project_id: str
    new: list[dict[str, Any]] = field(default_factory=list)
    fixed: list[dict[str, Any]] = field(default_factory=list)
    persisting: list[dict[str, Any]] = field(default_factory=list)
    requires_adjudication: list[tuple[dict[str, Any], dict[str, Any]]] = field(default_factory=list)
    unresolved_due_to_guard: list[tuple[dict[str, Any], dict[str, Any]]] = field(
        default_factory=list
    )

    @property
    def guard_blocked_count(self) -> int:
        return len(self.unresolved_due_to_guard)

    @property
    def new_count(self) -> int:
        return len(self.new)

    @property
    def fixed_count(self) -> int:
        return len(self.fixed)

    @property
    def persisting_count(self) -> int:
        return len(self.persisting)

    @property
    def pending_adjudication_count(self) -> int:
        return len(self.requires_adjudication)


def _require_db() -> Path:
    from core.config.database import _default_db_path

    return _default_db_path()


def _get_scan_findings(scan_id: str, db_path: Path) -> list[dict[str, Any]]:
    """Fetch all open findings for a scan from security_events spine.

    findings table was retired in migration 112 (WO-Y). findings_current_status
    (the spine read-model) was dropped in migration 140 (WO dff23cb0) — reads
    now derive current_status from security_events directly (see
    core/findings/current_status.py).
    """
    from core.findings.mutations import _get_conn
    from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL

    try:
        conn, owned = _get_conn(db_path)
        try:
            rows = conn.execute(
                f"SELECT fcs.finding_id, se.vuln_class AS rule_id,"
                "       fcs.file_path, fcs.line_number AS start_line,"
                "       NULL AS end_line, fcs.severity, se.vuln_class AS category,"
                "       se.title AS description, NULL AS recommendation,"
                "       NULL AS finding_hash, NULL AS normalized_snippet,"
                "       NULL AS code_excerpt, NULL AS enclosing_symbol"
                f" FROM ({FINDINGS_CURRENT_STATUS_SQL}) fcs"
                " JOIN security_events se ON se.event_id = fcs.finding_id"
                " JOIN security_events scan_root"
                "   ON scan_root.event_id = ?"
                "   AND se.parent_event_id = scan_root.event_id"
                " WHERE fcs.current_status != 'resolved'",
                (scan_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            if owned:
                conn.close()
    except Exception:
        return []


def _get_resolved_links(
    prev_scan_id: str,
    curr_scan_id: str,
    db_path: Path,
) -> list[dict[str, Any]]:
    """Fetch previously-adjudicated resolved events from security_events spine.

    resolved_finding_links was retired in migration 112 (WO-Y). Reads
    finding.resolved events from the spine as the equivalent.
    """
    from core.findings.mutations import _get_conn

    try:
        conn, owned = _get_conn(db_path)
        try:
            rows = conn.execute(
                "SELECT event_id AS link_id, parent_event_id AS prev_finding_id,"
                "       NULL AS curr_finding_id, body AS verdict, NULL AS confidence"
                " FROM security_events"
                " WHERE event_kind = 'finding.resolved'"
                "   AND parent_event_id IN ("
                "       SELECT event_id FROM security_events"
                "       WHERE parent_event_id = ? AND event_kind = 'finding.recorded'"
                "   )",
                (prev_scan_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            if owned:
                conn.close()
    except Exception:
        return []  # Spine may not exist on older schema versions


def compute_scan_delta(
    curr_scan_id: str,
    prev_scan_id: str,
    project_id: str,
    db_path: Path | None = None,
    *,
    line_proximity_window: int = 10,
) -> ScanDelta:
    """Compute baseline→delta between two consecutive scans.

    Returns a ScanDelta with findings categorized as new/fixed/persisting/
    requires_adjudication. The requires_adjudication list holds (prev, curr)
    pairs that need LLM adjudication (same rule+file+proximity, different hash).

    After adjudication, call finalize_adjudications() to apply verdicts and
    update the delta.
    """
    if db_path is None:
        db_path = _require_db()

    prev_findings = _get_scan_findings(prev_scan_id, db_path)
    curr_findings = _get_scan_findings(curr_scan_id, db_path)

    delta = ScanDelta(
        curr_scan_id=curr_scan_id,
        prev_scan_id=prev_scan_id,
        project_id=project_id,
    )

    # ── Step 1: Exact hash matching (bulk, free) ──────────────────────────────
    # findings with valid hashes that match exactly = persisting (no LLM needed)
    prev_by_hash: dict[str, dict] = {}
    for f in prev_findings:
        h = f.get("finding_hash")
        if h:
            prev_by_hash[h] = f

    curr_by_hash: dict[str, dict] = {}
    for f in curr_findings:
        h = f.get("finding_hash")
        if h:
            curr_by_hash[h] = f

    exact_match_hashes = set(prev_by_hash) & set(curr_by_hash)
    for h in exact_match_hashes:
        delta.persisting.append(curr_by_hash[h])

    matched_prev_ids: set[str] = {prev_by_hash[h]["finding_id"] for h in exact_match_hashes}
    matched_curr_ids: set[str] = {curr_by_hash[h]["finding_id"] for h in exact_match_hashes}

    # Unmatched after exact-hash pass
    possibly_fixed = [f for f in prev_findings if f["finding_id"] not in matched_prev_ids]
    possibly_new = [f for f in curr_findings if f["finding_id"] not in matched_curr_ids]

    # ── Step 2: Previously-adjudicated links (free, decided once) ─────────────
    resolved_links = _get_resolved_links(prev_scan_id, curr_scan_id, db_path)
    same_edited = {
        (r["prev_finding_id"], r["curr_finding_id"])
        for r in resolved_links
        if r["verdict"] == "same_edited"
    }
    # "distinct" verdicts leave findings in possibly_fixed/new — no set needed

    resolved_prev_ids = {pid for pid, _ in same_edited}
    resolved_curr_ids = {cid for _, cid in same_edited}

    for f in possibly_new:
        if f["finding_id"] in resolved_curr_ids:
            delta.persisting.append(f)
    possibly_fixed = [f for f in possibly_fixed if f["finding_id"] not in resolved_prev_ids]
    possibly_new = [f for f in possibly_new if f["finding_id"] not in resolved_curr_ids]

    # "distinct" adjudicated pairs stay in possibly_fixed/possibly_new (genuinely different)

    # ── Step 3: Pre-pair residuals by rule + file + line proximity ─────────────
    # Only pairs with same rule_id AND same file_path AND lines within window
    # become candidates for LLM adjudication. All others are settled as-is.
    candidate_pairs: list[tuple[dict, dict]] = []
    paired_prev_ids: set[str] = set()
    paired_curr_ids: set[str] = set()

    for prev_f in possibly_fixed:
        for curr_f in possibly_new:
            if (
                prev_f.get("rule_id") == curr_f.get("rule_id")
                and _normalized_path(prev_f.get("file_path"))
                == _normalized_path(curr_f.get("file_path"))
                and _line_proximity(
                    prev_f.get("start_line"), curr_f.get("start_line"), line_proximity_window
                )
                and prev_f["finding_id"] not in paired_prev_ids
                and curr_f["finding_id"] not in paired_curr_ids
            ):
                candidate_pairs.append((prev_f, curr_f))
                paired_prev_ids.add(prev_f["finding_id"])
                paired_curr_ids.add(curr_f["finding_id"])
                break  # Each prev finding pairs with at most one curr (greedy, closest first)

    # ── Step 4: Unpaired orphans = settled without LLM ────────────────────────
    for f in possibly_fixed:
        if f["finding_id"] not in paired_prev_ids:
            delta.fixed.append(f)  # No plausible partner → genuinely fixed

    for f in possibly_new:
        if f["finding_id"] not in paired_curr_ids:
            delta.new.append(f)  # No plausible predecessor → genuinely new

    # Candidate pairs need LLM adjudication
    delta.requires_adjudication = candidate_pairs

    return delta


def finalize_adjudications(
    delta: ScanDelta,
    adjudications: list[dict[str, Any]],
    db_path: Path | None = None,
) -> ScanDelta:
    """Apply LLM adjudication verdicts to a ScanDelta.

    adjudications: list of {"prev_finding_id": str, "curr_finding_id": str,
                              "verdict": "same_edited"|"distinct", "confidence": float}

    Updates delta.persisting, delta.new, delta.fixed based on verdicts.
    Persists verdicts to resolved_finding_links for future scans.

    Returns the updated delta (same object, mutated).
    """
    if db_path is None:
        db_path = _require_db()

    verdict_map: dict[tuple[str, str], str] = {}
    for a in adjudications:
        key = (a["prev_finding_id"], a["curr_finding_id"])
        verdict_map[key] = a.get("verdict", "distinct")

    # Build lookup for candidate pairs
    pair_lookup: dict[tuple[str, str], tuple[dict, dict]] = {}
    for prev_f, curr_f in delta.requires_adjudication:
        pair_lookup[(prev_f["finding_id"], curr_f["finding_id"])] = (prev_f, curr_f)

    remaining_pairs = []
    for (pid, cid), (prev_f, curr_f) in pair_lookup.items():
        verdict = verdict_map.get((pid, cid))
        if verdict == "same_edited":
            delta.persisting.append(curr_f)  # Same issue, just edited
        elif verdict == "distinct":
            delta.fixed.append(prev_f)  # Genuinely fixed
            delta.new.append(curr_f)  # Genuinely new
        else:
            remaining_pairs.append((prev_f, curr_f))  # Still pending

    delta.requires_adjudication = remaining_pairs

    # Persist verdicts
    _persist_adjudications(delta, adjudications, db_path)

    return delta


def _persist_adjudications(
    delta: ScanDelta,
    adjudications: list[dict[str, Any]],
    db_path: Path,
) -> None:
    """Write LLM adjudication verdicts as finding.resolved events on the security_events spine.

    resolved_finding_links was retired in migration 112 (WO-Y). Verdicts are now
    recorded via set_finding_status() on the security_events spine.
    """
    try:
        from core.findings.mutations import set_finding_status

        for a in adjudications:
            verdict = a.get("verdict", "distinct")
            if verdict == "same_edited":
                # Mark the prev finding as resolved (superseded by curr)
                set_finding_status(
                    a["prev_finding_id"],
                    "resolved",
                    project_id=delta.project_id,
                    reason=f"same_edited: superseded by {a['curr_finding_id']}",
                    db_path=db_path,
                )
    except Exception:
        pass  # Persistence failure is non-blocking


def persist_scan_delta(delta: ScanDelta, db_path: Path | None = None) -> str:
    """Record scan delta as a scan_run.started event on the security_events spine.

    scan_deltas was retired in migration 112 (WO-Y). Deltas are now derived from
    spine history by FindingsProjection. This function records a scan boundary
    event for lineage and returns a generated delta_id.
    """
    import uuid as _uuid
    from core.findings.mutations import _get_conn, _now

    delta_id = str(_uuid.uuid4())
    try:
        conn, owned = _get_conn(db_path)
        try:
            conn.execute(
                """INSERT OR IGNORE INTO security_events
                   (event_id, parent_event_id, event_kind, project_id, body, created_at)
                   VALUES (?, NULL, 'scan_run.started', ?, ?, ?)""",
                (
                    delta_id,
                    delta.project_id,
                    f"curr:{delta.curr_scan_id} prev:{delta.prev_scan_id}"
                    f" new:{delta.new_count} fixed:{delta.fixed_count}",
                    _now(),
                ),
            )
            if owned:
                conn.commit()
        finally:
            if owned:
                conn.close()
    except Exception:
        pass
    return delta_id


def get_latest_delta(project_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    """Return the most recent scan_run.started event for a project from security_events.

    scan_deltas was retired in migration 112 (WO-Y). Deltas are now derived from
    spine history. This returns the last scan boundary event.
    """
    from core.findings.mutations import _get_conn

    try:
        conn, owned = _get_conn(db_path)
        try:
            row = conn.execute(
                "SELECT event_id, project_id, body, created_at"
                " FROM security_events"
                " WHERE event_kind = 'scan_run.started' AND project_id = ?"
                " ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            if owned:
                conn.close()
    except Exception:
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _normalized_path(p: str | None) -> str:
    if not p:
        return ""
    return p.replace("\\", "/").strip()


def _line_proximity(line_a: int | None, line_b: int | None, window: int) -> bool:
    if line_a is None or line_b is None:
        return True  # Unknown lines: treat as proximate (conservative)
    return abs(line_a - line_b) <= window
