"""Causal integrity validation for decision-event links."""

from __future__ import annotations
from dataclasses import dataclass
from typing import List

from core.config.database import transaction, get_connection


@dataclass
class CausalIntegrityReport:
    """Report of causal link integrity."""

    orphan_events: List[str]
    orphan_decisions: List[str]
    broken_links: List[dict]
    integrity_score: float


# Event types that are explicitly non-decision events
NON_DECISION_EVENT_TYPES = {
    "system.startup",
    "system.shutdown",
    "metric.recorded",
    "log.written",
    "cache.hit",
    "cache.miss",
    "file.read",
    "file.written",
}


def validate_causal_integrity() -> CausalIntegrityReport:
    """Validate causal links between decisions and events.

    Returns:
        CausalIntegrityReport with identified integrity issues
    """
    with get_connection() as conn:
        # Find orphan events (events without causal decisions)
        orphan_events_rows = conn.execute("""SELECT e.event_id, e.event_type
               FROM canonical_events e
               WHERE e.event_type NOT IN ({})
               AND NOT EXISTS (
                   SELECT 1 FROM decision_event_link l
                   WHERE l.event_id = e.event_id
               )
               LIMIT 200""".format(",".join(f"'{t}'" for t in NON_DECISION_EVENT_TYPES))).fetchall()

        orphan_events = [f"{r[1]} ({r[0]})" for r in orphan_events_rows]

        # Find orphan decisions (decisions without event links)
        orphan_decisions_rows = conn.execute(
            """SELECT d.decision_id, d.decision_type, d.source_subsystem
               FROM decision_log d
               WHERE NOT EXISTS (
                   SELECT 1 FROM decision_event_link l
                   WHERE l.decision_id = d.decision_id
               )"""
        ).fetchall()

        orphan_decisions = [f"{r[1]} from {r[2]} ({r[0][:8]})" for r in orphan_decisions_rows]

        # Find broken links (links referencing non-existent IDs)
        broken_links_rows = conn.execute("""SELECT l.id, l.decision_id, l.event_id, l.relation_type
               FROM decision_event_link l
               WHERE NOT EXISTS (
                   SELECT 1 FROM decision_log d WHERE d.decision_id = l.decision_id
               )
               OR NOT EXISTS (
                   SELECT 1 FROM canonical_events e WHERE e.event_id = l.event_id
               )""").fetchall()

        broken_links = [
            {"link_id": r[0], "decision_id": r[1], "event_id": r[2], "relation_type": r[3]}
            for r in broken_links_rows
        ]

        # Calculate total events and decisions for scoring
        total_events = conn.execute(
            """SELECT COUNT(*) FROM canonical_events
               WHERE event_type NOT IN ({})""".format(
                ",".join(f"'{t}'" for t in NON_DECISION_EVENT_TYPES)
            )
        ).fetchone()[0]

        total_decisions = conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0]

    # Calculate integrity score
    # Score = (linked events + linked decisions) / (total events + total decisions)
    total_items = total_events + total_decisions
    orphaned_items = len(orphan_events) + len(orphan_decisions)

    if total_items > 0:
        integrity_score = 1.0 - (orphaned_items / total_items)
    else:
        integrity_score = 1.0

    return CausalIntegrityReport(
        orphan_events=orphan_events,
        orphan_decisions=orphan_decisions,
        broken_links=broken_links,
        integrity_score=max(0.0, min(1.0, integrity_score)),
    )


def mark_event_as_non_decision(event_id: str, reason: str) -> None:
    """Mark an event as explicitly non-decision (exemption).

    Args:
        event_id: Event ID to mark
        reason: Reason for exemption

    Note:
        This creates a special decision_event_link with relation_type="exempted"
    """
    with transaction() as conn:
        # Create exemption link
        conn.execute(
            """INSERT INTO decision_event_link
               (decision_id, event_id, relation_type)
               VALUES (?, ?, ?)""",
            ("EXEMPTED", event_id, f"exempted:{reason}"),
        )
