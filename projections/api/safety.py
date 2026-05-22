"""Dashboard data safety classification and filtering helpers.

Minimal classification system for Phase 5.6A dashboard safety hardening.
Prevents accidental exposure of private/internal data through the API.
"""

from __future__ import annotations

from typing import List

# ── Data Classification ─────────────────────────────────────────────────────

SAFE_LOCAL_SUMMARY = "safe_local_summary"
SENSITIVE_LOCAL_DETAIL = "sensitive_local_detail"
PRIVATE_INTERNAL = "private_internal"
UNSAFE_FOR_PILOT = "unsafe_for_pilot"


# ── Activity Log Filtering ──────────────────────────────────────────────────

PRIVATE_ACTIVITY_PREFIXES = (
    "internal.",
    "cognition.",
    "memory.private.",
    "private.",
    "debug.",
)

PRIVATE_ACTIVITY_TYPES = frozenset(
    {
        "memory_retrieval",
        "memory_consolidation",
        "cognition_trace",
        "private_audit",
        "internal_diagnostic",
    }
)


def activity_log_filter_clause(alias: str = "al", col: str = "activity_type") -> str:
    """Return a SQL WHERE fragment that excludes private activity types.

    Args:
        alias: table alias (default "al" for activity_log, use "ce" for canonical_events)
        col: event type column name (default "activity_type"; use "event_type" for canonical_events)

    Returns:
        SQL fragment like "AND al.activity_type NOT IN (...) AND ..."
    """
    type_col = f"{alias}.{col}"
    exclusions = ", ".join(f"'{t}'" for t in sorted(PRIVATE_ACTIVITY_TYPES))
    prefix_checks = " AND ".join(f"{type_col} NOT LIKE '{p}%'" for p in PRIVATE_ACTIVITY_PREFIXES)
    return f"AND {type_col} NOT IN ({exclusions}) AND {prefix_checks}"


# ── Decision Log Safety ─────────────────────────────────────────────────────

DECISION_LOG_SAFE_COLUMNS = ("decision_id", "decision_type", "confidence", "timestamp")
DECISION_LOG_PRIVATE_COLUMNS = ("reasoning", "context", "outcome")


# ── CORS ────────────────────────────────────────────────────────────────────

DEFAULT_DASHBOARD_PORT = 8000


def localhost_origins(port: int = DEFAULT_DASHBOARD_PORT) -> List[str]:
    """Return CORS origins for localhost on the given port."""
    return [
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
    ]


# ── Host Safety ─────────────────────────────────────────────────────────────

SAFE_DEFAULT_HOST = "127.0.0.1"
