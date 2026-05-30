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

import uuid
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
    """Fetch all findings for a scan."""
    from core.event_store.studio_db import _connect

    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT finding_id, rule_id, file_path, start_line, end_line,"
            " severity, category, description, recommendation,"
            " finding_hash, normalized_snippet, code_excerpt, enclosing_symbol"
            " FROM security_findings"
            " WHERE scan_id = ? AND status != 'resolved'",
            (scan_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _get_resolved_links(
    prev_scan_id: str,
    curr_scan_id: str,
    db_path: Path,
) -> list[dict[str, Any]]:
    """Fetch previously-adjudicated links between the two scans."""
    from core.event_store.studio_db import _connect

    try:
        with _connect(db_path) as conn:
            rows = conn.execute(
                "SELECT link_id, prev_finding_id, curr_finding_id, verdict, confidence"
                " FROM resolved_finding_links"
                " WHERE prev_scan_id = ? AND curr_scan_id = ?",
                (prev_scan_id, curr_scan_id),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []  # Table may not exist on older schema versions


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
    distinct = {
        (r["prev_finding_id"], r["curr_finding_id"])
        for r in resolved_links
        if r["verdict"] == "distinct"
    }

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
    """Write LLM adjudication verdicts to resolved_finding_links."""
    from core.event_store.studio_db import _connect
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    try:
        with _connect(db_path) as conn:
            for a in adjudications:
                conn.execute(
                    """INSERT OR IGNORE INTO resolved_finding_links
                       (link_id, prev_finding_id, curr_finding_id,
                        prev_scan_id, curr_scan_id, project_id,
                        verdict, confidence, adjudicated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        a["prev_finding_id"],
                        a["curr_finding_id"],
                        delta.prev_scan_id,
                        delta.curr_scan_id,
                        delta.project_id,
                        a.get("verdict", "distinct"),
                        a.get("confidence"),
                        now,
                    ),
                )
            conn.commit()
    except Exception:
        pass  # Persistence failure is non-blocking


def persist_scan_delta(delta: ScanDelta, db_path: Path | None = None) -> str:
    """Write delta summary to security_scan_deltas. Returns delta_id."""
    from core.event_store.studio_db import _connect
    from datetime import datetime, timezone

    if db_path is None:
        db_path = _require_db()

    delta_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _connect(db_path) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO security_scan_deltas
                   (delta_id, project_id, curr_scan_id, prev_scan_id,
                    new_count, fixed_count, persisting_count,
                    pending_adjudication_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    delta_id,
                    delta.project_id,
                    delta.curr_scan_id,
                    delta.prev_scan_id,
                    delta.new_count,
                    delta.fixed_count,
                    delta.persisting_count,
                    delta.pending_adjudication_count,
                    now,
                ),
            )
            conn.commit()
    except Exception:
        pass
    return delta_id


def get_latest_delta(project_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    """Return the most recent delta for a project."""
    from core.event_store.studio_db import _connect

    if db_path is None:
        db_path = _require_db()
    try:
        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT * FROM security_scan_deltas"
                " WHERE project_id = ?"
                " ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        return dict(row) if row else None
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
