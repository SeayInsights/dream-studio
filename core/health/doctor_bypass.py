"""Bypass-audit aggregation (WO-BYPASS-TELEMETRY).

Answers "which enforcement escape hatches fired, and how often" from the
canonical event spine. Two families:

- HOOK_EXECUTION_LOGGED records with ``trigger_context.decision == "bypass"``
  (``ai_canonical_events``): DS_ENFORCE=0 / tier=off short-circuits and
  fail-open allows (broken authority DB, enforcement-lib import failure),
  grouped by rule.
- ``gate.bypassed`` events (``business_canonical_events``): force-closes,
  MIGRATION_RISK_ACKNOWLEDGED, Docs-Reviewed-No-Change trailer consumption,
  grouped by gate.

The companion of the observe-tier ``observations_report``: bypasses may
exist — invisible bypasses may not. Consumed by ``ds doctor`` (bypass_audit
check) and ``ds project state`` (bypass_summary).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def bypass_audit(db_path: Path, *, since_days: int = 7) -> dict[str, Any]:
    """Aggregate recent bypass/fail-open records. Read-only; never raises."""
    since_iso = (datetime.now(UTC) - timedelta(days=since_days)).isoformat()
    result: dict[str, Any] = {
        "since": since_iso,
        "total": 0,
        "by_rule": {},
        "gate_bypasses": {},
    }
    try:
        conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        result["note"] = "authority DB unavailable"
        return result
    try:
        try:
            rows = conn.execute(
                "SELECT event_timestamp,"
                " json_extract(payload, '$.trigger_context.rule') AS rule,"
                " json_extract(payload, '$.trigger_context.detail') AS detail,"
                " json_extract(payload, '$.hook_name') AS hook_name"
                " FROM ai_canonical_events"
                " WHERE event_type = 'system.hook.execution.logged'"
                " AND json_extract(payload, '$.trigger_context.decision') = 'bypass'"
                " AND event_timestamp >= ?"
                " ORDER BY event_timestamp DESC",
                (since_iso,),
            ).fetchall()
        except sqlite3.Error:
            rows = []
        for row in rows:
            rule = row["rule"] or "unknown"
            bucket = result["by_rule"].setdefault(rule, {"count": 0, "samples": []})
            bucket["count"] += 1
            if len(bucket["samples"]) < 5:
                bucket["samples"].append(
                    {
                        "when": row["event_timestamp"],
                        "hook": row["hook_name"],
                        "detail": row["detail"],
                    }
                )
        result["total"] += len(rows)

        try:
            grows = conn.execute(
                "SELECT event_timestamp,"
                " json_extract(payload, '$.gate') AS gate,"
                " json_extract(payload, '$.reason') AS reason"
                " FROM business_canonical_events"
                " WHERE event_type = 'gate.bypassed' AND event_timestamp >= ?"
                " ORDER BY event_timestamp DESC",
                (since_iso,),
            ).fetchall()
        except sqlite3.Error:
            grows = []
        for row in grows:
            gate = row["gate"] or "unknown"
            bucket = result["gate_bypasses"].setdefault(gate, {"count": 0, "samples": []})
            bucket["count"] += 1
            if len(bucket["samples"]) < 5:
                bucket["samples"].append({"when": row["event_timestamp"], "reason": row["reason"]})
        result["total"] += len(grows)
    finally:
        conn.close()
    return result
