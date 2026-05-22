"""Risk scoring engine for security findings and events.

Standalone component that processes activity_log events and computes risk scores
based on file-level, project-level, and temporal risk factors.
"""

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from core.config.database import get_connection, transaction
from core.event_store import studio_db
from canonical.events.envelope import CanonicalEventEnvelope
from canonical.events.types import EventType as _CanonicalEventType
from emitters.shared.spool_writer import write_envelopes as _write_envelopes


def _default_db_path() -> Path:
    # Delegate to the canonical resolver in core.config.database so the
    # DREAM_STUDIO_DB_PATH env-var override is honored uniformly. Local
    # function preserved for backward-compat with existing callers below.
    from core.config.database import _default_db_path as _canonical_default_db_path

    return _canonical_default_db_path()


class RiskScoringEngine:
    """Compute and emit risk scores for events in the activity log."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize with database path.

        Args:
            db_path: Optional path to SQLite database containing activity_log.
                Defaults to the canonical local studio DB.
        """
        requested_path = Path(db_path).expanduser() if db_path is not None else None
        default_path = _default_db_path()
        self._explicit_db_path = (
            requested_path
            if requested_path is not None and requested_path != default_path
            else None
        )
        self.db_path = str(requested_path or default_path)

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with Row factory."""
        conn = (
            studio_db._connect(self._explicit_db_path)
            if self._explicit_db_path is not None
            else get_connection()
        )
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _transaction(self):
        """Write through the configured database authority."""
        if self._explicit_db_path is not None:
            with studio_db._db_transaction(self._explicit_db_path) as conn:
                yield conn
        else:
            with transaction() as conn:
                yield conn

    def fetch_unscored_events(self, limit: int = 100) -> List[Dict]:
        """Fetch events that need risk scoring.

        Queries canonical_events for events that:
        - Are security-related (event_type starts with 'security.')
        - Don't have a corresponding risk.score.computed event

        Args:
            limit: Maximum number of events to fetch

        Returns:
            List of event dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = """
        SELECT event_id, event_type, timestamp, payload, trace
        FROM canonical_events
        WHERE event_type LIKE 'security.%'
        AND event_id NOT IN (
            SELECT json_extract(payload, '$.source_event_id')
            FROM canonical_events
            WHERE event_type = 'risk.score.computed'
            AND json_extract(payload, '$.source_event_id') IS NOT NULL
        )
        ORDER BY timestamp DESC
        LIMIT ?
        """

        cursor.execute(query, (limit,))
        events = []
        for row in cursor.fetchall():
            d = dict(row)
            events.append(
                {
                    "activity_id": d.get("event_id"),  # event_id now serves as the ID
                    "activity_type": d.get("event_type"),
                    "event_timestamp": d.get("timestamp"),
                    "severity": "info",  # default; not stored in canonical_events separately
                    "stream_type": None,
                    "stream_id": None,
                    "event_data": d.get("payload"),  # payload is the JSON blob
                }
            )
        conn.close()

        return events

    def compute_risk_score(self, event: Dict) -> float:
        """Compute risk score for a single event (0-100).

        Risk is computed from three factors:
        - File-level risk (0-30): Findings in the file referenced by this event
        - Project-level risk (0-40): Total open findings across all files
        - Temporal risk (0-30): Recent spike in findings (last 24 hours)

        Args:
            event: Event dictionary from activity_log

        Returns:
            Risk score (0-100)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Extract file_path from event_data if present
        event_data = json.loads(event.get("event_data", "{}"))
        file_path = event_data.get("file_path")

        # File-level risk (0-30)
        file_risk = 0.0
        if file_path:
            cursor.execute(
                "SELECT COUNT(*) FROM sec_sarif_findings WHERE file_path = ? AND status = 'open'",
                (file_path,),
            )
            file_findings = cursor.fetchone()[0]
            # Scale: 0 findings = 0, 10+ findings = 30
            file_risk = min(30.0, file_findings * 3.0)

        # Project-level risk (0-40)
        cursor.execute("SELECT COUNT(*) FROM sec_sarif_findings WHERE status = 'open'")
        total_findings = cursor.fetchone()[0]
        # Scale: 0 findings = 0, 100+ findings = 40
        project_risk = min(40.0, total_findings * 0.4)

        # Temporal risk (0-30)
        # Count new findings in last 24 hours
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        cursor.execute("SELECT COUNT(*) FROM sec_sarif_findings WHERE created_at > ?", (yesterday,))
        recent_findings = cursor.fetchone()[0]
        # Scale: 0 recent = 0, 20+ recent = 30
        temporal_risk = min(30.0, recent_findings * 1.5)

        conn.close()

        # Total risk score (0-100)
        total_risk = file_risk + project_risk + temporal_risk
        return round(total_risk, 2)

    def emit_enriched_event(self, event: Dict, risk_score: float) -> None:
        """Emit enriched event to the canonical event spool.

        Creates a new RISK_SCORE_COMPUTED canonical event that references
        the original event and includes the computed risk score.

        Args:
            event: Original event dictionary
            risk_score: Computed risk score (0-100)
        """
        try:
            _write_envelopes(
                [
                    CanonicalEventEnvelope(
                        event_type=_CanonicalEventType.RISK_SCORE_COMPUTED.value,
                        session_id=None,
                        payload={
                            "source_event_type": event.get("activity_type"),
                            "risk_score": risk_score,
                            "computed_at": datetime.now().isoformat(),
                            "components": {
                                "file_level": (
                                    "file_path in original event"
                                    if json.loads(
                                        event.get("event_data") or event.get("payload") or "{}"
                                    ).get("file_path")
                                    else None
                                ),
                                "project_level": "total open findings",
                                "temporal": "findings in last 24h",
                            },
                        },
                        confidence="unavailable",
                        project_id=None,
                    )
                ]
            )
        except Exception:
            pass

    def run_forever(self, interval_sec: int = 300) -> None:
        """Main loop - run scoring every N seconds.

        Args:
            interval_sec: Sleep interval between scoring runs (default: 300s / 5min)
        """
        print(f"Risk scoring engine started (interval: {interval_sec}s)")

        while True:
            try:
                events = self.fetch_unscored_events()
                print(f"Processing {len(events)} unscored events...")

                for event in events:
                    score = self.compute_risk_score(event)
                    self.emit_enriched_event(event, score)
                    print(f"  Event {event['activity_id'][:12]}... → risk_score={score}")

                if events:
                    print(f"Scored {len(events)} events. Sleeping for {interval_sec}s...")
                else:
                    print(f"No events to score. Sleeping for {interval_sec}s...")

                time.sleep(interval_sec)

            except KeyboardInterrupt:
                print("Risk scoring engine stopped.")
                break
            except Exception as e:
                print(f"Error in scoring loop: {e}")
                time.sleep(interval_sec)
