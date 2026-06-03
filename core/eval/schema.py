"""Eval case schema — data structures for behavioral eval cases and results.

Eval cases are loaded from JSON files in the evals/ directory.
Each case defines: input, expected events (deterministic), expected behavior (LLM-judged),
and optional fixture data for Phase 1 simulation mode.
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

    # Scoring
    event_weight: float = 0.7
    behavior_weight: float = 0.3
    minimum_pass_score: float = 0.75

    # Expected outcomes
    expected_events: list[ExpectedEvent] = field(default_factory=list)
    expected_behavior: str = ""  # Natural language description for LLM judge
    negative_checks: list[str] = field(default_factory=list)

    # Phase 1 fixtures — pre-specified session output for testing without live Claude
    fixture_events: list[dict[str, Any]] | None = None  # Pre-specified events to match
    fixture_transcript: str | None = None  # Pre-specified session transcript for judge

    def total_weights(self) -> float:
        return self.event_weight + self.behavior_weight

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
        scoring = data.get("scoring", {})
        return cls(
            eval_id=data["eval_id"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            skill_id=data.get("skill_id"),
            input_prompt=data["input_prompt"],
            event_weight=scoring.get("event_weight", 0.7),
            behavior_weight=scoring.get("behavior_weight", 0.3),
            minimum_pass_score=scoring.get("minimum_pass_score", 0.75),
            expected_events=expected_events,
            expected_behavior=data.get("expected_behavior", ""),
            negative_checks=data.get("negative_checks", []),
            fixture_events=data.get("fixture_events"),
            fixture_transcript=data.get("fixture_transcript"),
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
class JudgeResult:
    """Result of LLM judge evaluation."""

    score: float | None  # None when judge was skipped
    rationale: str
    skipped: bool = False
    model_used: str = ""
    tokens_used: int = 0

    @property
    def effective_score(self) -> float:
        """Score for computation — 0.5 (neutral) when judge was skipped."""
        return self.score if self.score is not None else 0.5


@dataclass
class EvalResult:
    """Complete result for one eval case run."""

    eval_id: str
    version: str
    passed: bool
    composite_score: float  # Weighted event + behavior
    event_score: float
    behavior_score: float
    match_result: MatchResult
    judge_result: JudgeResult
    regression_flagged: bool = False
    baseline_score: float | None = None
    run_mode: str = "fixture"  # "fixture" | "live"
    error: str | None = None
    tokens_consumed: int = 0

    @property
    def score_display(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        reg = " [REGRESSION]" if self.regression_flagged else ""
        return (
            f"{status}{reg} — {self.composite_score:.2f} "
            f"(events: {self.event_score:.2f}, behavior: {self.behavior_score:.2f})"
        )
