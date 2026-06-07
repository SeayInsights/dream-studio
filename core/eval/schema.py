"""Eval case schema — data structures for behavioral eval cases and results.

Scoring is 100% deterministic: composite_score = event_score.
No LLM judge, no subprocess calls, no live sessions (WO-N2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExpectedEvent:
    """An event that must (or must not) appear in the captured event sequence."""

    event_type: str
    must_appear: bool = True  # False = negative check (must NOT appear)
    skill_id: str | None = None  # Optional: restrict match to this skill_id
    max_sequence_position: int | None = None  # Optional: event must appear within N events
    payload_contains: dict[str, Any] | None = None  # Optional: payload must contain these keys


@dataclass
class EvalCase:
    """A single behavioral eval case."""

    eval_id: str
    version: str
    description: str
    skill_id: str | None  # Primary skill being tested (may be None for routing tests)
    input_prompt: str

    # Scoring — 100% deterministic event matching
    event_weight: float = 1.0
    minimum_pass_score: float = 0.75

    # Expected outcomes
    expected_events: list[ExpectedEvent] = field(default_factory=list)

    # Optional human-readable notes (not used for scoring)
    notes: str = ""

    # Fixture events for unit/regression tests — pre-specified events to match
    fixture_events: list[dict[str, Any]] | None = None

    def total_weights(self) -> float:
        return self.event_weight

    @classmethod
    def from_json(cls, path: Path) -> "EvalCase":
        """Load an eval case from a JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        expected_events = [
            ExpectedEvent(
                event_type=e["event_type"],
                must_appear=e.get("must_appear", True),
                skill_id=e.get("skill_id"),
                max_sequence_position=e.get("max_sequence_position"),
                payload_contains=e.get("payload_contains"),
            )
            for e in data.get("expected_events", [])
        ]
        # Read scoring from top-level or legacy "scoring" sub-object
        scoring = data.get("scoring", {})
        event_weight = data.get("event_weight", scoring.get("event_weight", 1.0))
        minimum_pass_score = data.get("minimum_score", scoring.get("minimum_pass_score", 0.75))
        return cls(
            eval_id=data["eval_id"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            skill_id=data.get("skill_id"),
            input_prompt=data["input_prompt"],
            event_weight=event_weight,
            minimum_pass_score=minimum_pass_score,
            expected_events=expected_events,
            notes=data.get("notes", data.get("expected_behavior", "")),
            fixture_events=data.get("fixture_events"),
        )


@dataclass
class MatchResult:
    """Result of deterministic event matching."""

    score: float  # 0.0-1.0
    matched_required: int
    total_required: int
    negative_violations: list[str]  # Events that appeared but shouldn't have
    missing_events: list[str]  # Expected events that didn't appear
    out_of_order: list[str]  # Events present but in wrong position

    @property
    def is_perfect(self) -> bool:
        return (
            self.score == 1.0
            and not self.negative_violations
            and not self.missing_events
            and not self.out_of_order
        )


@dataclass
class EvalResult:
    """Complete result for one eval case run."""

    eval_id: str
    version: str
    passed: bool
    composite_score: float  # = event_score (100% deterministic)
    event_score: float
    match_result: MatchResult
    regression_flagged: bool = False
    baseline_score: float | None = None
    run_mode: str = "fixture"
    error: str | None = None
    tokens_consumed: int = 0  # Always 0 — no LLM calls

    @property
    def score_display(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        reg = " [REGRESSION]" if self.regression_flagged else ""
        return f"{status}{reg} — {self.composite_score:.2f} (events: {self.event_score:.2f})"
