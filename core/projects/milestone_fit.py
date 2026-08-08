"""Fit-check helper for WO/task attribution (Attribution Coherence, Phase 1).

The mis-attribution problem: work gets filed into whatever milestone is active just because the
user pivoted, so separate engagements (esp. consulting — one client, many projects) collapse
together. The fix is to compare a proposed WO against each candidate milestone's DESCRIBED scope
and ask instead of auto-filing when it does not clearly fit.

This module surfaces the raw material + a coarse, DETERMINISTIC fit signal (no LLM call): the
project's open milestones with their descriptions, a per-milestone fit level, and an overall
verdict that tells the attribution flow whether it can proceed or must stop and ask. The agent
(instructed by skill-text) makes the final semantic judgment; this gives it structured input and
a guardrail so a weak/ambiguous match is never silently auto-filed.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

# Generic project-management / English noise that must not count as topical overlap — otherwise
# every WO "fits" every milestone on words like "work", "build", "add".
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "into",
    "that",
    "this",
    "from",
    "not",
    "are",
    "was",
    "our",
    "work",
    "order",
    "orders",
    "task",
    "tasks",
    "milestone",
    "milestones",
    "project",
    "projects",
    "add",
    "adds",
    "added",
    "fix",
    "fixes",
    "fixed",
    "update",
    "updates",
    "build",
    "builds",
    "remove",
    "removes",
    "wire",
    "wires",
    "make",
    "makes",
    "use",
    "uses",
    "new",
    "via",
    "per",
    "all",
    "any",
    "its",
    "it",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "or",
    "is",
    "be",
    "so",
}

# A milestone counts as a "clear" fit at this many shared significant terms.
_CLEAR_MIN_SHARED = 2


def _terms(text: str) -> set[str]:
    """Significant lowercase word-stems (len >= 3, non-stopword) in *text*."""
    return {
        w
        for w in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", (text or "").lower())
        if w not in _STOPWORDS
    }


def _open_milestones(conn: sqlite3.Connection, project_id: str) -> list[tuple[str, str, str]]:
    rows = conn.execute(
        "SELECT milestone_id, title, COALESCE(description, '') FROM business_milestones"
        " WHERE project_id = ? AND status NOT IN ('complete', 'deleted')"
        " ORDER BY COALESCE(order_index, 0)",
        (project_id,),
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def candidate_milestones_for_work(
    project_id: str,
    work_title: str,
    work_description: str = "",
    *,
    db_path: Path | None = None,
) -> dict:
    """Return open milestones + a coarse fit signal for a proposed WO, to drive fit-check-and-ask.

    Shape::

        {
          "project_id": str,
          "candidates": [
            {"milestone_id", "title", "description", "fit": "clear|possible|none",
             "overlap_terms": [str, ...]},
            ...
          ],
          "verdict": "clear_single" | "ambiguous" | "no_fit" | "no_milestones",
          "best": milestone_id | None,   # highest-overlap candidate (None if zero overlap anywhere)
        }

    Fit is deterministic lexical overlap between the proposed work and each milestone's
    title+description. ``verdict`` guides the caller:
      - ``clear_single`` — exactly one clear fit; the attribution flow may proceed (still confirm).
      - ``ambiguous`` — multiple clear fits, or only weak/possible matches; the flow must ask.
      - ``no_fit`` — nothing overlaps; the flow must ask (offer a new milestone/project).
      - ``no_milestones`` — the project has no open milestone; the flow must ask/create.
    """
    from core.config.database import _default_db_path

    db = Path(db_path) if db_path is not None else _default_db_path()
    work_terms = _terms(f"{work_title} {work_description}")

    conn = sqlite3.connect(str(db))
    try:
        milestones = _open_milestones(conn, project_id)
    finally:
        conn.close()

    candidates: list[dict] = []
    for milestone_id, title, description in milestones:
        shared = sorted(work_terms & _terms(f"{title} {description}"))
        if len(shared) >= _CLEAR_MIN_SHARED:
            fit = "clear"
        elif shared:
            fit = "possible"
        else:
            fit = "none"
        candidates.append(
            {
                "milestone_id": milestone_id,
                "title": title,
                "description": description,
                "fit": fit,
                "overlap_terms": shared,
            }
        )

    clear = [c for c in candidates if c["fit"] == "clear"]
    possible = [c for c in candidates if c["fit"] == "possible"]
    best = max(candidates, key=lambda c: len(c["overlap_terms"]), default=None)
    best_id = best["milestone_id"] if best and best["overlap_terms"] else None

    if not candidates:
        verdict = "no_milestones"
    elif len(clear) == 1:
        verdict = "clear_single"
    elif clear or possible:
        verdict = "ambiguous"
    else:
        verdict = "no_fit"

    return {
        "project_id": project_id,
        "candidates": candidates,
        "verdict": verdict,
        "best": best_id,
    }
