"""Non-executing hardening loop helpers for shared intelligence records.

learning_event_records and hardening_candidate_records were dropped in
migration 131. Writer functions removed; validate_hardening_loop_report
is kept as a pure validator used by __init__.py exports.
"""

from __future__ import annotations

from typing import Any

ALLOWED_HARDENING_STATUSES: frozenset[str] = frozenset(
    {
        "candidate",
        "approved_for_rehearsal",
        "validated",
        "promoted",
        "rejected",
        "deferred",
    }
)


def validate_hardening_loop_report(report: dict[str, Any]) -> list[str]:
    """Validate that a hardening lifecycle report stays non-executing."""

    errors: list[str] = []
    if report.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if report.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    if report.get("routing_authority") is not False:
        errors.append("routing_authority must be false")
    if report.get("execution_authorized") is not False:
        errors.append("execution_authorized must be false")
    if report.get("candidate", {}).get("status") not in ALLOWED_HARDENING_STATUSES:
        errors.append("candidate status is not allowed")
    return errors
