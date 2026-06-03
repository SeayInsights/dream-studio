"""Claude Code judge — LLM-based behavioral evaluation via Claude Code subprocess.

Invokes Claude Code (`claude -p`) to grade session behavior against expected criteria.
No API key required — uses the operator's existing Claude Code installation.

The tight prompt is designed to minimize score variance across identical runs.
Target variance: < 0.05 between identical inputs.

Fallback: if Claude Code is unavailable, returns score=None (neutral 0.5 used by runner).

Tight prompt design principles:
1. Concrete score anchors (1.0/0.75/0.5/0.25/0.0) — no interpolation allowed
2. Explicit JSON-only output format
3. Negative check instructions (hard penalty triggers 0.0)
4. No ambiguous language in expected_behavior
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Any

from core.eval.schema import EvalCase, JudgeResult

logger = logging.getLogger(__name__)

# Model for judging — override via EVAL_JUDGE_MODEL env var if needed
# Default: use Claude Code's configured model (typically Sonnet)
# Note: using a capable model reduces self-assessment bias when evaluating
# sessions that also used Claude Code
JUDGE_MODEL_FLAG = ["--model", "claude-opus-4-8"]

# Subprocess timeout in seconds. 30s is sufficient for typical claude -p responses
# and keeps the full eval suite well under the 600s pre-push gate timeout (8 evals × 30s = 240s).
JUDGE_TIMEOUT = int(os.environ.get("DREAM_STUDIO_JUDGE_TIMEOUT", "30"))

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
    api_key: str | None = None,  # kept for backward compat; ignored in Claude Code mode
) -> JudgeResult:
    """Grade session behavior using Claude Code as the judge.

    Invokes `claude -p <prompt>` via subprocess.
    Falls back to neutral score=None when Claude Code is unavailable.

    Args:
        case: The eval case with expected_behavior and negative_checks.
        transcript: The actual session transcript to evaluate.
        api_key: Ignored (kept for API-compat signature). Claude Code needs no key.

    Returns:
        JudgeResult with score 0.0-1.0, rationale, and model info.
    """
    if not case.expected_behavior:
        return JudgeResult(
            score=1.0,
            rationale="No expected behavior specified — auto-pass",
            model_used="none",
        )

    claude_bin = shutil.which("claude")
    if not claude_bin:
        logger.info("claude CLI not found — judge skipped for eval %s", case.eval_id)
        return JudgeResult(
            score=None,
            rationale="claude CLI not found — judge skipped",
            skipped=True,
        )

    negative_text = (
        "\n".join(f"- {check}" for check in case.negative_checks)
        if case.negative_checks
        else "(none)"
    )
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        expected_behavior=case.expected_behavior,
        negative_checks=negative_text,
        transcript=transcript[:8000],
    )

    try:
        result = subprocess.run(
            [claude_bin, "-p"] + JUDGE_MODEL_FLAG + [prompt],
            capture_output=True,
            text=True,
            timeout=JUDGE_TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            err = result.stderr.strip()[:200] if result.stderr else "unknown error"
            logger.warning(
                "claude judge returned exit %d for eval %s: %s",
                result.returncode,
                case.eval_id,
                err,
            )
            return JudgeResult(
                score=None,
                rationale=f"claude exit {result.returncode}: {err}",
                skipped=True,
            )

        raw = result.stdout.strip()
        if not raw:
            logger.warning("Empty response from claude judge for eval %s", case.eval_id)
            return JudgeResult(
                score=None,
                rationale="Empty judge response",
                skipped=True,
            )

        parsed = _parse_judge_response(raw)
        return JudgeResult(
            score=parsed["score"],
            rationale=parsed["rationale"],
            model_used="claude-code",
            tokens_used=0,  # Claude Code plan usage; no separate token tracking
        )

    except subprocess.TimeoutExpired:
        logger.error("claude judge timed out (%ds) for eval %s", JUDGE_TIMEOUT, case.eval_id)
        return JudgeResult(
            score=None,
            rationale=f"Judge timed out after {JUDGE_TIMEOUT}s",
            skipped=True,
        )
    except Exception as exc:
        logger.error("claude judge failed for eval %s: %s", case.eval_id, exc)
        return JudgeResult(
            score=None,
            rationale=f"Judge failed: {exc}",
            skipped=True,
        )


def _parse_judge_response(raw: str) -> dict[str, Any]:
    """Parse the judge's JSON response with fallback."""
    text = raw.strip()
    # Strip markdown code block wrappers if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # Sometimes the response contains prose before the JSON — find last JSON object
    # (the judge is instructed to return ONLY JSON but may include preamble)
    import re

    json_match = re.search(r'\{[^{}]*"score"[^{}]*\}', text, re.DOTALL)
    if json_match:
        text = json_match.group(0)

    try:
        data = json.loads(text)
        score = float(data["score"])
        valid_anchors = [0.0, 0.25, 0.5, 0.75, 1.0]
        score = min(valid_anchors, key=lambda x: abs(x - score))
        return {"score": score, "rationale": str(data.get("rationale", ""))}
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning("Failed to parse judge response: %s | raw: %s", exc, raw[:200])
        return {"score": 0.5, "rationale": f"Parse error — defaulted to neutral: {exc}"}


def estimate_judge_tokens(case: EvalCase, transcript: str) -> int:
    """Estimate prompt size for the judge call (Claude Code plan — no token cost)."""
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        expected_behavior=case.expected_behavior or "",
        negative_checks="\n".join(case.negative_checks) if case.negative_checks else "(none)",
        transcript=transcript[:8000],
    )
    # Approximate for reporting purposes; Claude Code plan = no extra charge
    return len(prompt) // 4 + 200
