"""Friction signal harvester — Phase 19.2.

Detects three types of friction from existing telemetry via SQL heuristics.
No ML, no LLM at capture time — classification is 19.3's job.

Signal types:
  dismissed_finding   — finding dismissed by operator; skill produces false positives
  partial_completion  — scan completed but findings never engaged with (ignored)
  pattern_gap         — low-confidence workflow pattern; skill usage inconsistent

Threshold model (all must pass for a signal to be written):
  ≥ THRESHOLD_OCCURRENCES occurrences within WINDOW_DAYS
  ≥ THRESHOLD_SOURCES distinct source IDs (scans or patterns)
  Same skill_id across occurrences

Idempotency: INSERT OR IGNORE keyed on bucket_key (unique per signal type + skill + rule).
Running the harvester multiple times produces no duplicate rows.

Consumer contract for 19.3 Gap Classifier:
    SELECT * FROM ds_friction_signals
    WHERE classified_as IS NULL
    ORDER BY created_at
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

THRESHOLD_OCCURRENCES = 2
THRESHOLD_SOURCES = 2
WINDOW_DAYS = 30
LOW_CONFIDENCE_CEILING = 0.5
IGNORED_FINDING_STALE_DAYS = 7


def _bucket_key(signal_type: str, skill_id: str | None, rule_id: str | None = None) -> str:
    raw = f"{signal_type}:{skill_id or ''}:{rule_id or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass
class HarvestResult:
    signals_written: int = 0
    signals_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signals_written": self.signals_written,
            "signals_skipped": self.signals_skipped,
            "errors": self.errors,
        }


class FrictionSignalHarvester:
    """Harvests friction signals from existing telemetry tables."""

    def __init__(self, conn: sqlite3.Connection, session_id: str | None = None) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.session_id = session_id

    def harvest(self, project_id: str | None = None) -> HarvestResult:
        result = HarvestResult()

        for detector, name in [
            (self._detect_dismissed_findings, "dismissed_finding"),
            (self._detect_partial_completions, "partial_completion"),
            (self._detect_pattern_gaps, "pattern_gap"),
        ]:
            try:
                rows = detector(project_id)
                for row in rows:
                    written = self._write_signal(row)
                    if written:
                        result.signals_written += 1
                    else:
                        result.signals_skipped += 1
            except Exception as exc:
                msg = f"{name} detection failed: {exc}"
                logger.warning(msg)
                result.errors.append(msg)

        logger.info(
            "FrictionSignalHarvester: wrote=%d skipped=%d errors=%d (session=%s)",
            result.signals_written,
            result.signals_skipped,
            len(result.errors),
            self.session_id or "none",
        )
        return result

    # ── Detectors ──────────────────────────────────────────────────────────

    def _detect_dismissed_findings(
        self, project_id: str | None
    ) -> list[dict[str, Any]]:
        """Findings dismissed by operator — skill produces too many false positives.

        Threshold: ≥2 dismissed findings for the same (introduced_by_skill_id, rule_id)
        across ≥2 distinct scan_ids within the last 30 days.
        """
        params: list[Any] = [THRESHOLD_SOURCES, THRESHOLD_OCCURRENCES]
        project_clause = ""
        if project_id:
            project_clause = "AND project_id = ? "
            params = [project_id] + params

        sql = f"""
            SELECT
                COALESCE(introduced_by_skill_id, 'unknown') AS skill_id,
                COALESCE(rule_id, '')                       AS rule_id,
                COUNT(DISTINCT scan_id)                     AS source_cnt,
                COUNT(*)                                    AS occurrence_cnt,
                MAX(dismissed_at)                           AS last_dismissed,
                COALESCE(project_id, '')                    AS project_id
            FROM findings
            WHERE dismissed_at IS NOT NULL
              AND dismissed_at >= datetime('now', '-{WINDOW_DAYS} days')
              {project_clause}
            GROUP BY introduced_by_skill_id, rule_id
            HAVING source_cnt >= ?
               AND occurrence_cnt >= ?
        """
        rows = self.conn.execute(sql, params).fetchall()
        signals = []
        for r in rows:
            bk = _bucket_key("dismissed_finding", r["skill_id"], r["rule_id"] or None)
            signals.append(
                {
                    "signal_type": "dismissed_finding",
                    "skill_id": r["skill_id"],
                    "rule_id": r["rule_id"] or None,
                    "source_table": "findings",
                    "source_id": bk,
                    "project_id": r["project_id"] or None,
                    "bucket_key": bk,
                    "context": json.dumps(
                        {
                            "occurrence_count": r["occurrence_cnt"],
                            "distinct_scans": r["source_cnt"],
                            "last_dismissed": r["last_dismissed"],
                        }
                    ),
                }
            )
        return signals

    def _detect_partial_completions(
        self, project_id: str | None
    ) -> list[dict[str, Any]]:
        """Scans completed with findings that were never engaged with.

        A finding is 'ignored' when it is still open, not dismissed,
        and was created more than IGNORED_FINDING_STALE_DAYS ago.
        Threshold: ≥2 such scans for the same skill_id.
        """
        params: list[Any] = [THRESHOLD_SOURCES, THRESHOLD_OCCURRENCES]
        project_clause = ""
        if project_id:
            project_clause = "AND sr.project_id = ? "
            params = [project_id] + params

        sql = f"""
            SELECT
                COALESCE(sr.skill_id, 'unknown') AS skill_id,
                COUNT(DISTINCT sr.scan_id)       AS source_cnt,
                COUNT(DISTINCT f.finding_id)     AS finding_cnt,
                COALESCE(sr.project_id, '')      AS project_id
            FROM scan_runs sr
            JOIN findings f ON f.scan_id = sr.scan_id
            WHERE sr.status = 'completed'
              AND sr.findings_count > 0
              AND f.status = 'open'
              AND (f.dismissed_at IS NULL OR f.dismissed_at = '')
              AND f.created_at <= datetime('now', '-{IGNORED_FINDING_STALE_DAYS} days')
              AND f.created_at >= datetime('now', '-{WINDOW_DAYS + IGNORED_FINDING_STALE_DAYS} days')
              {project_clause}
            GROUP BY sr.skill_id
            HAVING source_cnt >= ?
               AND finding_cnt >= ?
        """
        rows = self.conn.execute(sql, params).fetchall()
        signals = []
        for r in rows:
            bk = _bucket_key("partial_completion", r["skill_id"])
            signals.append(
                {
                    "signal_type": "partial_completion",
                    "skill_id": r["skill_id"],
                    "rule_id": None,
                    "source_table": "scan_runs",
                    "source_id": bk,
                    "project_id": r["project_id"] or None,
                    "bucket_key": bk,
                    "context": json.dumps(
                        {
                            "occurrence_count": r["finding_cnt"],
                            "distinct_scans": r["source_cnt"],
                        }
                    ),
                }
            )
        return signals

    def _detect_pattern_gaps(
        self, project_id: str | None
    ) -> list[dict[str, Any]]:
        """Low-confidence workflow patterns — skill usage is inconsistent.

        Reads ds_workflow_pattern_signals WHERE confidence_score < LOW_CONFIDENCE_CEILING
        AND co_occurrence_count >= THRESHOLD_SOURCES. These are patterns that were
        attempted but never stabilized, indicating the skill is being invoked in
        inconsistent contexts.
        """
        params: list[Any] = [LOW_CONFIDENCE_CEILING, THRESHOLD_SOURCES]
        project_clause = ""
        if project_id:
            project_clause = "AND project_id = ? "
            params = [project_id] + params

        try:
            self.conn.execute(
                "SELECT 1 FROM ds_workflow_pattern_signals LIMIT 1"
            )
        except sqlite3.OperationalError:
            logger.debug("ds_workflow_pattern_signals not available — skipping pattern_gap")
            return []

        sql = f"""
            SELECT
                pattern_id,
                skill_a                 AS skill_id,
                project_id,
                confidence_score,
                co_occurrence_count,
                pattern_type,
                last_observed_at
            FROM ds_workflow_pattern_signals
            WHERE confidence_score < ?
              AND suppressed = 0
              AND co_occurrence_count >= ?
              AND last_observed_at >= datetime('now', '-{WINDOW_DAYS} days')
              {project_clause}
        """
        rows = self.conn.execute(sql, params).fetchall()
        signals = []
        for r in rows:
            bk = _bucket_key("pattern_gap", r["skill_id"], r["pattern_id"])
            signals.append(
                {
                    "signal_type": "pattern_gap",
                    "skill_id": r["skill_id"],
                    "rule_id": None,
                    "source_table": "ds_workflow_pattern_signals",
                    "source_id": r["pattern_id"],
                    "project_id": r["project_id"] or None,
                    "bucket_key": bk,
                    "context": json.dumps(
                        {
                            "confidence_score": r["confidence_score"],
                            "co_occurrence_count": r["co_occurrence_count"],
                            "pattern_type": r["pattern_type"],
                            "last_observed_at": r["last_observed_at"],
                        }
                    ),
                }
            )
        return signals

    # ── Write ──────────────────────────────────────────────────────────────

    def _write_signal(self, signal: dict[str, Any]) -> bool:
        """Insert signal if bucket_key not already present. Returns True if written."""
        try:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO ds_friction_signals (
                    signal_id, session_id, project_id, signal_type,
                    skill_id, rule_id, source_table, source_id,
                    context, bucket_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    str(uuid.uuid4()),
                    self.session_id,
                    signal.get("project_id"),
                    signal["signal_type"],
                    signal.get("skill_id"),
                    signal.get("rule_id"),
                    signal["source_table"],
                    signal["source_id"],
                    signal.get("context", "{}"),
                    signal["bucket_key"],
                ),
            )
            self.conn.commit()
            return self.conn.execute(
                "SELECT changes()"
            ).fetchone()[0] > 0
        except Exception as exc:
            logger.warning(
                "Failed to write friction signal (type=%s skill=%s): %s",
                signal.get("signal_type"),
                signal.get("skill_id"),
                exc,
            )
            return False

    # ── Read ──────────────────────────────────────────────────────────────

    def get_unclassified(
        self,
        signal_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """19.3 consumer contract: unclassified signals ordered by created_at."""
        params: list[Any] = []
        type_clause = ""
        if signal_type:
            type_clause = "AND signal_type = ? "
            params.append(signal_type)
        params.append(limit)
        rows = self.conn.execute(
            f"""
            SELECT * FROM ds_friction_signals
            WHERE classified_as IS NULL
              {type_clause}
            ORDER BY created_at
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
