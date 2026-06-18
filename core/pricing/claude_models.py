"""Claude model pricing reference data.

Prices are per 1,000,000 tokens (MTok) in USD.
Source: https://platform.claude.com/docs/en/docs/about-claude/pricing
Verified: 2026-05-22
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

# Per-model pricing in USD per 1M tokens.
# Keys are canonical model IDs as returned by the Claude API.
# cache_write = 5-minute cache write price (the standard tier).
CLAUDE_MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-8": {
        # Current Opus tier — same published rates as opus-4-5/4-6/4-7.
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_read": 0.50,
    },
    "claude-opus-4-7": {
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_read": 0.50,
    },
    "claude-opus-4-6": {
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_read": 0.50,
    },
    "claude-opus-4-5": {
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_read": 0.50,
    },
    "claude-opus-4-1": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
    "claude-opus-4": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-sonnet-4-5": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-sonnet-4": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10,
    },
    "claude-haiku-3-5": {
        "input": 0.80,
        "output": 4.00,
        "cache_write": 1.00,
        "cache_read": 0.08,
    },
}


def _normalize_model_id(model: str) -> str:
    """Strip date suffixes like -20251001 from model IDs for pricing lookup.

    claude-haiku-4-5-20251001 → claude-haiku-4-5
    claude-sonnet-4-6         → claude-sonnet-4-6 (unchanged)
    """
    import re

    return re.sub(r"-\d{8}$", "", model.strip().lower())


def compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Return USD cost for a single token.consumed event.

    Prices are per 1M tokens; this divides by 1_000_000 internally.
    If the model is not in the pricing table, returns 0.0 and logs an anomaly.
    """
    if not model:
        return 0.0

    normalized = _normalize_model_id(model)
    pricing = CLAUDE_MODEL_PRICING.get(normalized)

    if pricing is None:
        _log.warning("compute_cost: unknown model %r — returning 0.0 cost", model)
        return 0.0

    cost = (
        input_tokens * pricing["input"]
        + output_tokens * pricing["output"]
        + cache_creation_tokens * pricing["cache_write"]
        + cache_read_tokens * pricing["cache_read"]
    ) / 1_000_000

    return cost
