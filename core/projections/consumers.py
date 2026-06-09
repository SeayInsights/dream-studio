"""Built-in projection consumers — materialized views for operational intelligence.

Each projection subscribes to specific event types and maintains a summary table
that can be queried without scanning the full event stream.
"""

import json
import sqlite3
from typing import Any, Dict, List

from core.projections.framework import Projection


class WorkflowProjection(Projection):
    """Tracks workflow execution: success rates, durations, failure patterns."""

    @property
    def name(self) -> str:
        return "workflow_execution"

    @property
    def event_types(self) -> List[str]:
        return ["workflow.%"]

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proj_workflow_runs (
                workflow_id TEXT PRIMARY KEY,
                workflow_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                duration_seconds REAL,
                nodes_total INTEGER DEFAULT 0,
                nodes_completed INTEGER DEFAULT 0,
                nodes_failed INTEGER DEFAULT 0,
                failure_reason TEXT,
                event_id_start TEXT,
                event_id_end TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_proj_wf_status
            ON proj_workflow_runs(status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_proj_wf_name
            ON proj_workflow_runs(workflow_name)
        """)

    def handle(self, event: Dict[str, Any], conn: sqlite3.Connection) -> int:
        payload = event["payload"]
        etype = event["event_type"]

        if etype in ("workflow.started", "workflow.created"):
            wf_id = payload.get("workflow_id", event["event_id"])
            conn.execute(
                """
                INSERT OR IGNORE INTO proj_workflow_runs
                    (workflow_id, workflow_name, status, started_at, event_id_start)
                VALUES (?, ?, 'running', ?, ?)
            """,
                (
                    wf_id,
                    payload.get("workflow_name", "unknown"),
                    event["timestamp"],
                    event["event_id"],
                ),
            )
            return 1

        if etype in ("workflow.completed", "workflow.finished"):
            wf_id = payload.get("workflow_id", "")
            conn.execute(
                """
                UPDATE proj_workflow_runs SET
                    status = 'completed', completed_at = ?, event_id_end = ?,
                    duration_seconds = CASE
                        WHEN started_at IS NOT NULL
                        THEN (julianday(?) - julianday(started_at)) * 86400
                        ELSE NULL END,
                    nodes_completed = COALESCE(?, nodes_completed)
                WHERE workflow_id = ?
            """,
                (
                    event["timestamp"],
                    event["event_id"],
                    event["timestamp"],
                    payload.get("nodes_completed"),
                    wf_id,
                ),
            )
            return 1

        if etype == "workflow.failed":
            wf_id = payload.get("workflow_id", "")
            conn.execute(
                """
                UPDATE proj_workflow_runs SET
                    status = 'failed', completed_at = ?, event_id_end = ?,
                    failure_reason = ?,
                    nodes_failed = COALESCE(?, nodes_failed)
                WHERE workflow_id = ?
            """,
                (
                    event["timestamp"],
                    event["event_id"],
                    payload.get("error", payload.get("reason")),
                    payload.get("nodes_failed"),
                    wf_id,
                ),
            )
            return 1

        if etype == "workflow.node.completed":
            wf_id = payload.get("workflow_id", "")
            conn.execute(
                """
                UPDATE proj_workflow_runs SET
                    nodes_completed = nodes_completed + 1
                WHERE workflow_id = ?
            """,
                (wf_id,),
            )
            return 1

        return 0

    def pre_rebuild(self, conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM proj_workflow_runs")


class SkillRoutingProjection(Projection):
    """Tracks skill invocations: frequency, model usage, correction rates."""

    @property
    def name(self) -> str:
        return "skill_routing"

    @property
    def event_types(self) -> List[str]:
        return ["skill.%"]

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proj_skill_stats (
                skill_name TEXT NOT NULL,
                mode TEXT NOT NULL,
                period TEXT NOT NULL,
                invocations INTEGER DEFAULT 0,
                corrections INTEGER DEFAULT 0,
                avg_confidence REAL,
                models_used TEXT,
                last_invoked TEXT,
                PRIMARY KEY (skill_name, mode, period)
            )
        """)

    def handle(self, event: Dict[str, Any], conn: sqlite3.Connection) -> int:
        payload = event["payload"]
        etype = event["event_type"]

        skill = payload.get("skill", payload.get("skill_name", "unknown"))
        mode = payload.get("mode", "default")
        period = event["timestamp"][:10]  # YYYY-MM-DD

        if etype in (
            "skill.invoked",
            "skill.started",
            "skill.completed",
            "skill.execution.started",
            "skill.execution.completed",
        ):
            model = payload.get("model", "")
            confidence = event.get("confidence_score")

            conn.execute(
                """
                INSERT INTO proj_skill_stats
                    (skill_name, mode, period, invocations, avg_confidence, models_used, last_invoked)
                VALUES (?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(skill_name, mode, period) DO UPDATE SET
                    invocations = invocations + 1,
                    avg_confidence = CASE
                        WHEN ? IS NOT NULL
                        THEN (COALESCE(avg_confidence, 0) * invocations + ?) / (invocations + 1)
                        ELSE avg_confidence END,
                    models_used = CASE
                        WHEN models_used IS NULL THEN ?
                        WHEN instr(models_used, ?) = 0 THEN models_used || ',' || ?
                        ELSE models_used END,
                    last_invoked = ?
            """,
                (
                    skill,
                    mode,
                    period,
                    confidence,
                    json.dumps([model]) if model else None,
                    event["timestamp"],
                    confidence,
                    confidence,
                    model,
                    model,
                    model,
                    event["timestamp"],
                ),
            )
            return 1

        if etype in ("skill.corrected", "skill.correction"):
            conn.execute(
                """
                UPDATE proj_skill_stats SET
                    corrections = corrections + 1
                WHERE skill_name = ? AND mode = ? AND period = ?
            """,
                (skill, mode, period),
            )
            return 1

        return 0

    def pre_rebuild(self, conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM proj_skill_stats")


class SessionProjection(Projection):
    """Tracks session lifecycle and context efficiency."""

    @property
    def name(self) -> str:
        return "session_analytics"

    @property
    def event_types(self) -> List[str]:
        return ["session.%"]

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proj_sessions (
                session_id TEXT PRIMARY KEY,
                started_at TEXT,
                ended_at TEXT,
                duration_seconds REAL,
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                skills_used TEXT,
                compactions INTEGER DEFAULT 0,
                handoff_created INTEGER DEFAULT 0,
                event_id_start TEXT,
                event_id_end TEXT
            )
        """)

    def handle(self, event: Dict[str, Any], conn: sqlite3.Connection) -> int:
        payload = event["payload"]
        etype = event["event_type"]
        sid = payload.get("session_id", event["event_id"])

        if etype in ("session.started", "session.created"):
            conn.execute(
                """
                INSERT OR IGNORE INTO proj_sessions
                    (session_id, started_at, event_id_start)
                VALUES (?, ?, ?)
            """,
                (sid, event["timestamp"], event["event_id"]),
            )
            return 1

        if etype in ("session.ended", "session.completed"):
            conn.execute(
                """
                UPDATE proj_sessions SET
                    ended_at = ?, event_id_end = ?,
                    duration_seconds = CASE
                        WHEN started_at IS NOT NULL
                        THEN (julianday(?) - julianday(started_at)) * 86400
                        ELSE NULL END,
                    tokens_in = COALESCE(?, tokens_in),
                    tokens_out = COALESCE(?, tokens_out)
                WHERE session_id = ?
            """,
                (
                    event["timestamp"],
                    event["event_id"],
                    event["timestamp"],
                    payload.get("input_tokens"),
                    payload.get("output_tokens"),
                    sid,
                ),
            )
            return 1

        if etype == "session.compacted":
            conn.execute(
                """
                UPDATE proj_sessions SET compactions = compactions + 1
                WHERE session_id = ?
            """,
                (sid,),
            )
            return 1

        if etype == "session.handoff.created":
            conn.execute(
                """
                UPDATE proj_sessions SET handoff_created = 1
                WHERE session_id = ?
            """,
                (sid,),
            )
            return 1

        return 0

    def pre_rebuild(self, conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM proj_sessions")


class DecisionProjection(Projection):
    """Aggregates decision patterns for intelligence analysis."""

    @property
    def name(self) -> str:
        return "decision_intelligence"

    @property
    def event_types(self) -> List[str]:
        return ["decision.%", "skill.mode.unlocked"]

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proj_decision_patterns (
                decision_type TEXT NOT NULL,
                subsystem TEXT NOT NULL,
                period TEXT NOT NULL,
                total_decisions INTEGER DEFAULT 0,
                avg_confidence REAL,
                low_confidence_count INTEGER DEFAULT 0,
                policies_applied TEXT,
                PRIMARY KEY (decision_type, subsystem, period)
            )
        """)

    def handle(self, event: Dict[str, Any], conn: sqlite3.Connection) -> int:
        payload = event["payload"]
        decision_type = payload.get("decision_type", event["event_type"])
        subsystem = payload.get("subsystem", event.get("source_type", "unknown"))
        period = event["timestamp"][:10]
        confidence = payload.get("confidence", event.get("confidence_score"))
        policy = payload.get("policy_applied", "")
        low_conf = 1 if confidence is not None and confidence < 0.5 else 0

        conn.execute(
            """
            INSERT INTO proj_decision_patterns
                (decision_type, subsystem, period, total_decisions,
                 avg_confidence, low_confidence_count, policies_applied)
            VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(decision_type, subsystem, period) DO UPDATE SET
                total_decisions = total_decisions + 1,
                avg_confidence = CASE
                    WHEN ? IS NOT NULL
                    THEN (COALESCE(avg_confidence, 0) * total_decisions + ?) / (total_decisions + 1)
                    ELSE avg_confidence END,
                low_confidence_count = low_confidence_count + ?,
                policies_applied = CASE
                    WHEN ? != '' AND (policies_applied IS NULL OR instr(policies_applied, ?) = 0)
                    THEN COALESCE(policies_applied || ',' || ?, ?)
                    ELSE policies_applied END
        """,
            (
                decision_type,
                subsystem,
                period,
                confidence,
                low_conf,
                policy,
                confidence,
                confidence,
                low_conf,
                policy,
                policy,
                policy,
                policy,
            ),
        )
        return 1

    def pre_rebuild(self, conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM proj_decision_patterns")


class SecurityProjection(Projection):
    """Tracks security events: scans, findings, compliance changes."""

    @property
    def name(self) -> str:
        return "security_events"

    @property
    def event_types(self) -> List[str]:
        return ["security.%"]

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proj_security_summary (
                project_id TEXT NOT NULL,
                period TEXT NOT NULL,
                scans_run INTEGER DEFAULT 0,
                findings_total INTEGER DEFAULT 0,
                findings_critical INTEGER DEFAULT 0,
                findings_high INTEGER DEFAULT 0,
                findings_resolved INTEGER DEFAULT 0,
                last_scan_at TEXT,
                PRIMARY KEY (project_id, period)
            )
        """)

    def handle(self, event: Dict[str, Any], conn: sqlite3.Connection) -> int:
        payload = event["payload"]
        project_id = payload.get("project_id", payload.get("project", "unknown"))
        period = event["timestamp"][:10]
        etype = event["event_type"]

        if "scan" in etype:
            findings = payload.get("findings_count", 0)
            critical = payload.get("critical_count", 0)
            high = payload.get("high_count", 0)

            conn.execute(
                """
                INSERT INTO proj_security_summary
                    (project_id, period, scans_run, findings_total,
                     findings_critical, findings_high, last_scan_at)
                VALUES (?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(project_id, period) DO UPDATE SET
                    scans_run = scans_run + 1,
                    findings_total = findings_total + ?,
                    findings_critical = findings_critical + ?,
                    findings_high = findings_high + ?,
                    last_scan_at = ?
            """,
                (
                    project_id,
                    period,
                    findings,
                    critical,
                    high,
                    event["timestamp"],
                    findings,
                    critical,
                    high,
                    event["timestamp"],
                ),
            )
            return 1

        if "resolved" in etype or "mitigated" in etype:
            conn.execute(
                """
                UPDATE proj_security_summary SET
                    findings_resolved = findings_resolved + 1
                WHERE project_id = ? AND period = ?
            """,
                (project_id, period),
            )
            return 1

        return 0

    def pre_rebuild(self, conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM proj_security_summary")


def get_default_engine():
    """Create a ProjectionEngine with all built-in projections registered."""
    from core.projections.framework import ProjectionEngine

    engine = ProjectionEngine()
    engine.register(WorkflowProjection())
    engine.register(SkillRoutingProjection())
    engine.register(SessionProjection())
    engine.register(DecisionProjection())
    engine.register(SecurityProjection())
    return engine
