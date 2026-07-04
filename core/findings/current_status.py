"""Read-time derivation of "current status" for findings recorded on the
security_events spine (WO dff23cb0-950f-4607-bb30-e1a353a6f8ba, migration 140).

findings_current_status used to be a materialized SQLite table, upserted by
FindingsProjection.fold_spine() (core/projections/findings_projection.py,
deleted by this same change) on every projection-runner cycle: one row per
finding.recorded event, with current_status folded from the latest
finding.status_changed / finding.resolved event body for that finding (or
'open' if none exists yet). Every column was reconstructable from
security_events — it was pure derived state duplicating its source — so
migration 140 dropped the table.

FINDINGS_CURRENT_STATUS_SQL reproduces the identical one-row-per-finding_id
shape (finding_id, project_id, work_order_id, severity, title, file_path,
line_number, scanner_type, current_status, last_status_event_id, created_at,
updated_at) as a plain SQL SELECT, computed fresh on every query — no table,
no stored rows. This mirrors the precedent set by migration 139 for
decision_records/outcome_records/dashboard_attention_items (see
core/telemetry/read_models.py::_DECISION_EVENTS_VIEW_SQL and friends): a
derived-view SQL fragment that callers wrap as a subquery,
`FROM ({FINDINGS_CURRENT_STATUS_SQL}) fcs`, in place of the dropped table name.
"""

from __future__ import annotations

import sqlite3

# current_status derivation matches FindingsProjection.fold_spine() exactly:
# the latest finding.status_changed / finding.resolved event (by created_at,
# event_id tiebreak) whose parent_event_id is the finding.recorded event_id;
# its body is "new_status" or "new_status: reason" (split on ':', trimmed).
# No matching status event → 'open' (the column default the table used to
# carry). updated_at was "now() at last fold" on the table; the closest
# honest read-time equivalent is the timestamp of the latest status event,
# falling back to the finding's own created_at when there is none.
FINDINGS_CURRENT_STATUS_SQL = """
    SELECT
        r.event_id AS finding_id,
        r.project_id AS project_id,
        r.work_order_id AS work_order_id,
        r.severity AS severity,
        r.title AS title,
        r.file_path AS file_path,
        r.line_number AS line_number,
        r.scanner_type AS scanner_type,
        CASE
            WHEN ls.body IS NULL THEN 'open'
            ELSE TRIM(
                CASE WHEN INSTR(ls.body, ':') > 0
                     THEN SUBSTR(ls.body, 1, INSTR(ls.body, ':') - 1)
                     ELSE ls.body
                END
            )
        END AS current_status,
        ls.event_id AS last_status_event_id,
        r.created_at AS created_at,
        COALESCE(ls.created_at, r.created_at) AS updated_at
    FROM (
        SELECT * FROM security_events WHERE event_kind = 'finding.recorded'
    ) r
    LEFT JOIN (
        SELECT parent_event_id, body, event_id, created_at,
               ROW_NUMBER() OVER (
                   PARTITION BY parent_event_id ORDER BY created_at DESC, event_id DESC
               ) AS rn
        FROM security_events
        WHERE event_kind IN ('finding.status_changed', 'finding.resolved')
    ) ls ON ls.parent_event_id = r.event_id AND ls.rn = 1
"""


def security_spine_present(conn: sqlite3.Connection) -> bool:
    """True if security_events (the source table FINDINGS_CURRENT_STATUS_SQL
    derives from) exists in this schema snapshot.

    Equivalent presence gate to the old object_exists(conn,
    "findings_current_status") check: security_events and
    findings_current_status were created by the same migration-111 DDL
    statement and were never independently present/absent.
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'security_events'"
    ).fetchone()
    return row is not None
