"""Workflow pattern analyzer — SQL heuristics over canonical_events.

Detects three types of skill co-occurrence patterns:
  post_completion  — skill consistently invoked after work_order.closed
  pre_close        — skill consistently invoked just before work_order.closed
  always_paired    — two skills almost always invoked together within the same session

Detection is cheap SQL over existing canonical_events. No ML, no LLM.
Results stored in ds_workflow_pattern_signals for Phase 19 consumption.

─── Session derivation ──────────────────────────────────────────────────────

Sessions are derived from system.session.recorded and system.session.closed
events that are already emitted into canonical_events. The session_id for
each event is the event_id of the most recent system.session.recorded event
before it, scoped to the same project_id.

A system.session.closed event closes the session boundary — events after it
but before a new system.session.recorded are excluded from pattern detection.

Open sessions (system.session.recorded with no later system.session.closed or
system.session.recorded) are treated as still-active. Events in an open
session are included in pattern detection with the current analysis run time
as the implicit boundary.

─── Schema ──────────────────────────────────────────────────────────────────

Reads from canonical_events using json_extract() for trace fields:
  skill_id  = json_extract(trace, '$.skill_specifier')
  project_id = json_extract(trace, '$.project_id')

There is one schema. Tests insert events with full trace JSON blobs.

─── Confidence formula ───────────────────────────────────────────────────────

always_paired:
    confidence = co_sessions / max(sessions_with_a, sessions_with_b)
    Using max() as denominator: the rarer skill drives confidence, so a skill
    that always co-occurs with a more common one still scores near 1.0.

post_completion / pre_close:
    confidence = sessions_where_skill_appeared / total_sessions_with_close

─── Phase 19 contract ───────────────────────────────────────────────────────

    SELECT * FROM ds_workflow_pattern_signals
    WHERE confidence_score >= 0.8 AND suppressed = 0
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

MIN_OCCURRENCES = 2
WINDOW_MINUTES = 60

EVENT_SKILL_INVOKED = "skill.invoked"
EVENT_SESSION_STARTED = "system.session.recorded"
EVENT_SESSION_CLOSED = "system.session.closed"
EVENT_WO_CLOSED = "work_order.closed"


def _pattern_id(
    pattern_type: str, skill_a: str, skill_b: str | None, project_id: str | None
) -> str:
    raw = f"{pattern_type}|{skill_a}|{skill_b or ''}|{project_id or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


# ── Session derivation CTE ────────────────────────────────────────────────
#
# Inlines into each pattern query. Derives session boundaries from
# system.session.recorded / system.session.closed events.

_SESSION_CTE = f"""
    session_boundaries AS (
        -- Each system.session.recorded event starts a session.
        -- The session ends at the next session event (recorded or closed)
        -- for the same project, or stays open if none follows.
        SELECT
            s.event_id                                      AS session_id,
            COALESCE(json_extract(s.trace, '$.project_id'),
                     'unknown')                             AS project_id,
            s.created_at                                    AS session_start,
            COALESCE(
                (
                    SELECT MIN(nx.created_at)
                    FROM canonical_events nx
                    WHERE nx.event_type IN ('{EVENT_SESSION_STARTED}',
                                            '{EVENT_SESSION_CLOSED}')
                      AND COALESCE(json_extract(nx.trace, '$.project_id'),
                                   'unknown') =
                          COALESCE(json_extract(s.trace,  '$.project_id'),
                                   'unknown')
                      AND nx.created_at > s.created_at
                ),
                '9999-12-31T23:59:59'   -- open session: no later boundary
            )                                               AS session_end
        FROM canonical_events s
        WHERE s.event_type = '{EVENT_SESSION_STARTED}'
    )
"""


class WorkflowPatternAnalyzer:
    """Detects workflow patterns from canonical_events via SQL heuristics."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def analyze(
        self,
        project_id: str | None = None,
        min_occurrences: int = MIN_OCCURRENCES,
        min_confidence: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Detect all three pattern types and upsert results.

        Args:
            project_id: Restrict to one project. None = all projects.
            min_occurrences: Minimum co-occurrence count to surface a pattern.
            min_confidence: Minimum confidence to store (default 0.3 — stores
                even weak patterns; Phase 19 reads >= 0.8 only).

        Returns:
            List of signal dicts detected and upserted.
        """
        signals: list[dict[str, Any]] = []

        for detector, name in [
            (self._detect_always_paired, "always_paired"),
            (self._detect_post_completion, "post_completion"),
            (self._detect_pre_close, "pre_close"),
        ]:
            try:
                signals.extend(detector(project_id, min_occurrences, min_confidence))
            except Exception as exc:
                logger.warning("%s detection failed: %s", name, exc)

        for sig in signals:
            self._upsert_signal(sig)

        logger.info(
            "WorkflowPatternAnalyzer: %d signals (project=%s)",
            len(signals),
            project_id or "all",
        )
        return signals

    # ── Detectors ──────────────────────────────────────────────────────────

    def _detect_always_paired(
        self, project_id: str | None, min_occ: int, min_conf: float
    ) -> list[dict[str, Any]]:
        """Skills A and B almost always appear together in the same session."""
        proj_filter = "AND es.project_id = ?" if project_id else ""
        params: list[Any] = [min_occ]
        if project_id:
            # Insert before min_occ in params list
            params = [] + ([project_id] if project_id else []) + [min_occ]
        params.append(min_conf)

        sql = f"""
            WITH {_SESSION_CTE},
            event_sessions AS (
                SELECT
                    e.event_id,
                    e.event_type,
                    e.created_at,
                    json_extract(e.trace, '$.skill_specifier') AS skill_id,
                    COALESCE(json_extract(e.trace, '$.project_id'),
                             'unknown')                       AS project_id,
                    sb.session_id
                FROM canonical_events e
                JOIN session_boundaries sb
                  ON COALESCE(json_extract(e.trace, '$.project_id'),
                               'unknown') = sb.project_id
                  AND datetime(e.created_at) >= datetime(sb.session_start)
                  AND datetime(e.created_at) <  datetime(sb.session_end)
                WHERE e.event_type = ?
                  AND json_extract(e.trace, '$.skill_specifier') IS NOT NULL
            ),
            skill_sessions AS (
                SELECT DISTINCT project_id, session_id, skill_id
                FROM event_sessions
                {"WHERE project_id = ?" if project_id else ""}
            ),
            pairs AS (
                SELECT
                    a.project_id,
                    a.skill_id AS skill_a,
                    b.skill_id AS skill_b,
                    COUNT(DISTINCT a.session_id) AS co_sessions
                FROM skill_sessions a
                JOIN skill_sessions b
                  ON a.session_id = b.session_id
                  AND a.project_id = b.project_id
                  AND a.skill_id < b.skill_id
                GROUP BY a.project_id, a.skill_id, b.skill_id
                HAVING co_sessions >= ?
            ),
            total_per_skill AS (
                SELECT project_id, skill_id,
                       COUNT(DISTINCT session_id) AS total_sessions
                FROM skill_sessions
                GROUP BY project_id, skill_id
            )
            SELECT
                p.project_id,
                p.skill_a,
                p.skill_b,
                p.co_sessions            AS co_occurrence_count,
                MAX(ta.total_sessions,
                    tb.total_sessions)   AS total_sessions,
                ROUND(
                    CAST(p.co_sessions AS REAL) /
                    MAX(ta.total_sessions, tb.total_sessions),
                    4
                )                        AS confidence_score
            FROM pairs p
            JOIN total_per_skill ta
              ON p.project_id = ta.project_id AND p.skill_a = ta.skill_id
            JOIN total_per_skill tb
              ON p.project_id = tb.project_id AND p.skill_b = tb.skill_id
            WHERE ROUND(
                CAST(p.co_sessions AS REAL) /
                MAX(ta.total_sessions, tb.total_sessions), 4
            ) >= ?
            ORDER BY confidence_score DESC
        """

        # Params: EVENT_SKILL_INVOKED, [project_id once for skill_sessions], min_occ, min_conf
        all_params: list[Any] = [EVENT_SKILL_INVOKED]
        if project_id:
            all_params.append(project_id)
        all_params.extend([min_occ, min_conf])

        rows = self.conn.execute(sql, all_params).fetchall()
        return [
            {
                "pattern_id": _pattern_id(
                    "always_paired", r["skill_a"], r["skill_b"], r["project_id"]
                ),
                "project_id": r["project_id"],
                "pattern_type": "always_paired",
                "skill_a": r["skill_a"],
                "skill_b": r["skill_b"],
                "co_occurrence_count": r["co_occurrence_count"],
                "total_sessions": r["total_sessions"],
                "confidence_score": r["confidence_score"],
            }
            for r in rows
        ]

    def _detect_post_completion(
        self, project_id: str | None, min_occ: int, min_conf: float
    ) -> list[dict[str, Any]]:
        """Skill consistently invoked after work_order.closed, within WINDOW_MINUTES."""
        proj_skill_filter = "AND json_extract(e.trace, '$.project_id') = ?" if project_id else ""
        proj_close_filter = (
            "AND json_extract(close_e.trace, '$.project_id') = ?" if project_id else ""
        )

        # EVENT_SESSION_STARTED is embedded in _SESSION_CTE as a literal (not ?)
        all_params: list[Any] = [EVENT_WO_CLOSED]
        if project_id:
            all_params.append(project_id)
        all_params.extend([EVENT_SKILL_INVOKED, WINDOW_MINUTES])
        if project_id:
            all_params.append(project_id)
        all_params.extend([min_occ, min_conf])

        sql = f"""
            WITH {_SESSION_CTE},
            close_events AS (
                SELECT
                    ce.event_id AS close_id,
                    ce.created_at AS close_at,
                    COALESCE(json_extract(ce.trace, '$.project_id'),
                             'unknown') AS project_id,
                    sb.session_id
                FROM canonical_events ce
                JOIN session_boundaries sb
                  ON COALESCE(json_extract(ce.trace, '$.project_id'),
                               'unknown') = sb.project_id
                  AND datetime(ce.created_at) >= datetime(sb.session_start)
                  AND datetime(ce.created_at) <  datetime(sb.session_end)
                WHERE ce.event_type = ?
                {proj_close_filter}
            ),
            post_skills AS (
                SELECT
                    ce.project_id,
                    ce.session_id,
                    json_extract(e.trace, '$.skill_specifier') AS skill_id
                FROM close_events ce
                JOIN canonical_events e
                  ON COALESCE(json_extract(e.trace, '$.project_id'),
                               'unknown') = ce.project_id
                  AND e.event_type = ?
                  -- Use datetime() on both sides to normalize T vs space separator
                  AND datetime(e.created_at) > datetime(ce.close_at)
                  AND datetime(e.created_at) <=
                      datetime(ce.close_at, '+' || ? || ' minutes')
                WHERE json_extract(e.trace, '$.skill_specifier') IS NOT NULL
                {proj_skill_filter}
            ),
            agg AS (
                SELECT project_id, skill_id,
                       COUNT(DISTINCT session_id) AS co_occurrence_count
                FROM post_skills
                GROUP BY project_id, skill_id
                HAVING co_occurrence_count >= ?
            ),
            total_closes AS (
                SELECT project_id, COUNT(DISTINCT session_id) AS close_count
                FROM close_events
                GROUP BY project_id
            )
            SELECT
                a.project_id,
                a.skill_id AS skill_a,
                a.co_occurrence_count,
                tc.close_count AS total_sessions,
                ROUND(CAST(a.co_occurrence_count AS REAL) /
                      tc.close_count, 4) AS confidence_score
            FROM agg a
            JOIN total_closes tc ON a.project_id = tc.project_id
            WHERE confidence_score >= ?
            ORDER BY confidence_score DESC
        """

        rows = self.conn.execute(sql, all_params).fetchall()
        return [
            {
                "pattern_id": _pattern_id("post_completion", r["skill_a"], None, r["project_id"]),
                "project_id": r["project_id"],
                "pattern_type": "post_completion",
                "skill_a": r["skill_a"],
                "skill_b": None,
                "co_occurrence_count": r["co_occurrence_count"],
                "total_sessions": r["total_sessions"],
                "confidence_score": r["confidence_score"],
            }
            for r in rows
        ]

    def _detect_pre_close(
        self, project_id: str | None, min_occ: int, min_conf: float
    ) -> list[dict[str, Any]]:
        """Skill consistently invoked just before work_order.closed."""
        proj_skill_filter = "AND json_extract(e.trace, '$.project_id') = ?" if project_id else ""
        proj_close_filter = (
            "AND json_extract(close_e.trace, '$.project_id') = ?" if project_id else ""
        )

        # EVENT_SESSION_STARTED is embedded in _SESSION_CTE as a literal (not ?)
        all_params: list[Any] = [EVENT_WO_CLOSED]
        if project_id:
            all_params.append(project_id)
        all_params.extend([EVENT_SKILL_INVOKED, WINDOW_MINUTES])
        if project_id:
            all_params.append(project_id)
        all_params.extend([min_occ, min_conf])

        sql = f"""
            WITH {_SESSION_CTE},
            close_events AS (
                SELECT
                    ce.event_id AS close_id,
                    ce.created_at AS close_at,
                    COALESCE(json_extract(ce.trace, '$.project_id'),
                             'unknown') AS project_id,
                    sb.session_id
                FROM canonical_events ce
                JOIN session_boundaries sb
                  ON COALESCE(json_extract(ce.trace, '$.project_id'),
                               'unknown') = sb.project_id
                  AND datetime(ce.created_at) >= datetime(sb.session_start)
                  AND datetime(ce.created_at) <  datetime(sb.session_end)
                WHERE ce.event_type = ?
                {proj_close_filter}
            ),
            pre_skills AS (
                SELECT
                    ce.project_id,
                    ce.session_id,
                    json_extract(e.trace, '$.skill_specifier') AS skill_id
                FROM close_events ce
                JOIN canonical_events e
                  ON COALESCE(json_extract(e.trace, '$.project_id'),
                               'unknown') = ce.project_id
                  AND e.event_type = ?
                  -- Use datetime() on both sides to normalize T vs space separator
                  AND datetime(e.created_at) < datetime(ce.close_at)
                  AND datetime(e.created_at) >=
                      datetime(ce.close_at, '-' || ? || ' minutes')
                WHERE json_extract(e.trace, '$.skill_specifier') IS NOT NULL
                {proj_skill_filter}
            ),
            agg AS (
                SELECT project_id, skill_id,
                       COUNT(DISTINCT session_id) AS co_occurrence_count
                FROM pre_skills
                GROUP BY project_id, skill_id
                HAVING co_occurrence_count >= ?
            ),
            total_closes AS (
                SELECT project_id, COUNT(DISTINCT session_id) AS close_count
                FROM close_events
                GROUP BY project_id
            )
            SELECT
                a.project_id,
                a.skill_id AS skill_a,
                a.co_occurrence_count,
                tc.close_count AS total_sessions,
                ROUND(CAST(a.co_occurrence_count AS REAL) /
                      tc.close_count, 4) AS confidence_score
            FROM agg a
            JOIN total_closes tc ON a.project_id = tc.project_id
            WHERE confidence_score >= ?
            ORDER BY confidence_score DESC
        """

        rows = self.conn.execute(sql, all_params).fetchall()
        return [
            {
                "pattern_id": _pattern_id("pre_close", r["skill_a"], None, r["project_id"]),
                "project_id": r["project_id"],
                "pattern_type": "pre_close",
                "skill_a": r["skill_a"],
                "skill_b": None,
                "co_occurrence_count": r["co_occurrence_count"],
                "total_sessions": r["total_sessions"],
                "confidence_score": r["confidence_score"],
            }
            for r in rows
        ]

    # ── Storage & retrieval ────────────────────────────────────────────────

    def _upsert_signal(self, signal: dict[str, Any]) -> None:
        try:
            self.conn.execute(
                """
                INSERT INTO ds_workflow_pattern_signals
                    (pattern_id, project_id, pattern_type, skill_a, skill_b,
                     co_occurrence_count, total_sessions, confidence_score,
                     last_observed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(pattern_id) DO UPDATE SET
                    co_occurrence_count = excluded.co_occurrence_count,
                    total_sessions      = excluded.total_sessions,
                    confidence_score    = excluded.confidence_score,
                    last_observed_at    = datetime('now')
                WHERE suppressed = 0
                """,
                (
                    signal["pattern_id"],
                    signal.get("project_id"),
                    signal["pattern_type"],
                    signal["skill_a"],
                    signal.get("skill_b"),
                    signal["co_occurrence_count"],
                    signal["total_sessions"],
                    signal["confidence_score"],
                ),
            )
            self.conn.commit()
        except Exception as exc:
            logger.warning("Failed to upsert signal %s: %s", signal["pattern_id"], exc)

    def suppress_pattern(self, pattern_id: str) -> bool:
        cursor = self.conn.execute(
            "UPDATE ds_workflow_pattern_signals "
            "SET suppressed = 1, suppressed_at = datetime('now') "
            "WHERE pattern_id = ?",
            (pattern_id,),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_patterns(
        self,
        project_id: str | None = None,
        include_suppressed: bool = False,
        min_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if not include_suppressed:
            conditions.append("suppressed = 0")
        if min_confidence > 0:
            conditions.append("confidence_score >= ?")
            params.append(min_confidence)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        try:
            rows = self.conn.execute(
                f"SELECT * FROM ds_workflow_pattern_signals {where} "
                f"ORDER BY confidence_score DESC",
                params,
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []
