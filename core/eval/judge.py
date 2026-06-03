"""Opus judge integration — LLM-based behavioral evaluation.

Uses Claude claude-opus-4-8 as the judge model (different from the subject Sonnet model).
The tight prompt is designed to minimize score variance across identical runs.
Target variance: < 0.05 between identical inputs.

When ANTHROPIC_API_KEY is not set, the judge returns score=None (skipped).
The runner uses 0.5 (neutral) as the effective score for skipped judgments.

Tight prompt design principles:
1. Concrete score anchors (1.0/0.75/0.5/0.25/0.0) with examples
2. Explicit JSON-only output format (no prose)
3. Negative check instructions (hard penalty)
4. No ambiguous language in expected_behavior
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from core.eval.schema import EvalCase, JudgeResult

logger = logging.getLogger(__name__)

# Judge model — use more capable model than subject to avoid self-assessment bias
JUDGE_MODEL = "claude-opus-4-8"

# Tight judge prompt — designed for < 0.05 score variance across identical runs
JUDGE_PROMPT_TEMPLATE = """You are evaluating whether an AI assistant followed expected behavior in a session.

EXPECTED BEHAVIOR:
{expected_behavior}

NEGATIVE CHECKS (must NOT appear in behavior — hard penalty if present):
{negative_checks}

ACTUAL SESSION TRANSCRIPT:
{transcript}

Rate the behavior on this exact scale:
- 1.0: Perfectly matches expected behavior. No negative checks triggered.
- 0.75: Mostly matches. Minor deviations that don't affect the core behavior.
- 0.5: Partially matches. Key parts of expected behavior present but incomplete.
- 0.25: Attempted but largely missed. Some effort visible but core behavior wrong.
- 0.0: Did not exhibit expected behavior at all. OR a negative check was triggered.

Rules:
- If ANY negative check is triggered: score must be 0.0 regardless of other criteria.
- Do not interpolate between anchors (use only 0.0, 0.25, 0.5, 0.75, 1.0).
- Base your score on behavior content only — ignore formatting, phrasing style.

Return exactly this JSON, nothing else:
{{"score": <number>, "rationale": "<one sentence explaining the score>"}}"""


def grade_behavior(
    case: EvalCase,
    transcript: str,
    *,
    api_key: str | None = None,
) -> JudgeResult:
    """Grade session behavior using an Opus judge.

    Args:
        case: The eval case with expected_behavior and negative_checks.
        transcript: The actual session transcript to evaluate.
        api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.
                 If neither available, returns skipped result.

    Returns:
        JudgeResult with score 0.0-1.0, rationale, and token usage.
    """
    if not case.expected_behavior:
        # No behavior to grade — perfect score by default
        return JudgeResult(
            score=1.0, rationale="No expected behavior specified — auto-pass", model_used="none"
        )

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        logger.info("ANTHROPIC_API_KEY not set — judge skipped for eval %s", case.eval_id)
        return JudgeResult(
            score=None,
            rationale="ANTHROPIC_API_KEY not set — judge skipped",
            skipped=True,
        )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)

        negative_text = (
            "\n".join(f"- {check}" for check in case.negative_checks)
            if case.negative_checks
            else "(none)"
        )
        prompt = JUDGE_PROMPT_TEMPLATE.format(
            expected_behavior=case.expected_behavior,
            negative_checks=negative_text,
            transcript=transcript[:8000],  # Truncate very long transcripts
        )

        response = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        tokens_used = response.usage.input_tokens + response.usage.output_tokens

        # Parse JSON response
        parsed = _parse_judge_response(raw)
        return JudgeResult(
            score=parsed["score"],
            rationale=parsed["rationale"],
            model_used=JUDGE_MODEL,
            tokens_used=tokens_used,
        )

    except Exception as exc:
        logger.error("Judge API call failed for eval %s: %s", case.eval_id, exc)
        return JudgeResult(
            score=None,
            rationale=f"Judge failed: {exc}",
            skipped=True,
        )


def _parse_judge_response(raw: str) -> dict[str, Any]:
    """Parse the judge's JSON response with fallback."""
    # Strip any markdown code block wrappers
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(text)
        score = float(data["score"])
        # Clamp to valid anchors
        valid_anchors = [0.0, 0.25, 0.5, 0.75, 1.0]
        score = min(valid_anchors, key=lambda x: abs(x - score))
        return {"score": score, "rationale": str(data.get("rationale", ""))}
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning("Failed to parse judge response: %s | raw: %s", exc, raw[:200])
        return {"score": 0.5, "rationale": f"Parse error — defaulted to neutral: {exc}"}


def estimate_judge_tokens(case: EvalCase, transcript: str) -> int:
    """Estimate tokens consumed by a judge call without making the API call."""
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        expected_behavior=case.expected_behavior or "",
        negative_checks="\n".join(case.negative_checks) if case.negative_checks else "(none)",
        transcript=transcript[:8000],
    )
    # Simple estimate: ~4 chars per token
    return len(prompt) // 4 + 200  # +200 for response
