"""Deterministic event matcher — compares captured events against expected sequence.

The matcher is fully deterministic: same input always produces same score.
No LLM involvement. Score represents how well the captured events match
the eval case's expected_events specification.

Scoring rules:
- Required event present: +1 credit
- Required event absent: 0 credit
- Negative event present: deduct from score
- Sequence position violation: partial credit (0.5 instead of 1.0)

Final score: (credits) / (total required events)
"""

from __future__ import annotations

import logging
from typing import Any

from core.eval.schema import EvalCase, ExpectedEvent, MatchResult

logger = logging.getLogger(__name__)


def match_events(case: EvalCase, captured_events: list[dict[str, Any]]) -> MatchResult:
    """Compare captured events against expected events in an eval case.

    Args:
        case: The eval case with expected_events defined.
        captured_events: List of event dicts captured during the session.
            Each event must have at minimum an 'event_type' key.

    Returns:
        MatchResult with score and detailed breakdown.
    """
    if not case.expected_events:
        # No events expected — perfect match by default
        return MatchResult(
            score=1.0,
            matched_required=0,
            total_required=0,
            negative_violations=[],
            missing_events=[],
            out_of_order=[],
        )

    required_events = [e for e in case.expected_events if e.must_appear]
    forbidden_events = [e for e in case.expected_events if not e.must_appear]

    # ── Check required events ─────────────────────────────────────────────
    matched = 0
    missing = []
    out_of_order = []
    credits = 0.0

    for i, expected in enumerate(required_events):
        found_idx = _find_event(expected, captured_events)
        if found_idx is None:
            missing.append(
                f"{expected.event_type}" + (f"[{expected.skill_id}]" if expected.skill_id else "")
            )
            # 0 credit for missing required event
        else:
            matched += 1
            # Check sequence position
            if (
                expected.max_sequence_position is not None
                and found_idx > expected.max_sequence_position
            ):
                out_of_order.append(
                    f"{expected.event_type} at position {found_idx} (expected within {expected.max_sequence_position})"
                )
                credits += 0.5  # Partial credit for out-of-order
            else:
                credits += 1.0  # Full credit

    total_required = len(required_events)
    base_score = credits / total_required if total_required > 0 else 1.0

    # ── Check negative events (must NOT appear) ───────────────────────────
    violations = []
    for forbidden in forbidden_events:
        found_idx = _find_event(forbidden, captured_events)
        if found_idx is not None:
            violations.append(
                f"{forbidden.event_type}"
                + (f"[{forbidden.skill_id}]" if forbidden.skill_id else "")
            )

    # Negative violations reduce the score
    violation_penalty = len(violations) * 0.2  # Each violation costs 0.2
    final_score = max(0.0, base_score - violation_penalty)

    return MatchResult(
        score=round(final_score, 4),
        matched_required=matched,
        total_required=total_required,
        negative_violations=violations,
        missing_events=missing,
        out_of_order=out_of_order,
    )


def _find_event(expected: ExpectedEvent, events: list[dict[str, Any]]) -> int | None:
    """Find an expected event in the captured event list. Returns index or None."""
    for i, evt in enumerate(events):
        if evt.get("event_type") != expected.event_type:
            continue
        # Optional skill_id filter
        if expected.skill_id is not None:
            evt_skill = evt.get("skill_id") or evt.get("trace", {}).get("skill_id", "")
            if expected.skill_id not in evt_skill:
                continue
        # Optional payload_contains check
        if expected.payload_contains:
            payload = evt.get("payload", {}) or evt.get("data", {}) or {}
            if not _dict_contains(payload, expected.payload_contains):
                continue
        return i
    return None


def _dict_contains(obj: dict, subset: dict) -> bool:
    """Return True if obj contains all key-value pairs in subset."""
    for key, val in subset.items():
        if key not in obj:
            return False
        if isinstance(val, dict) and isinstance(obj[key], dict):
            if not _dict_contains(obj[key], val):
                return False
        elif obj[key] != val:
            return False
    return True
