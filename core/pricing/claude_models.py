"""Claude model pricing reference data.

Prices are per 1,000,000 tokens (MTok) in USD.
Source: https://platform.claude.com/docs/en/docs/about-claude/pricing
Verified: 2026-09-17

A model missing from this table costs $0.00, which is indistinguishable from
"free" on every downstream surface. That has now silently zeroed the cost
panel twice — first when claude-opus-4-8 shipped (WO-COST-MODEL-RATES), then
again across the 5-series rollover, which left 99.2% of recorded token events
priced at zero for four months.

The guard against a third occurrence is NOT this docstring and NOT a hardcoded
list of "current" models: it is tests/unit/test_claude_models_pricing.py, which
derives the models to check from the model_ids actually present in the event
store. Any model real usage records must price here, or that test fails.
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)


class UnknownModelPricing(LookupError):
    """Raised by compute_cost(strict=True) for a model absent from the table.

    Callers that report money use strict=True so a missing rate surfaces as a
    failure rather than as $0.00.
    """


# Per-model pricing in USD per 1M tokens.
# Keys are canonical model IDs as returned by the Claude API.
# cache_write = 5-minute cache write price (the standard tier).
# cache_read is the published per-model rate (normally 0.1x input, but the
# Fable 5.1 tier prices cache reads below that ratio — do not derive it).
CLAUDE_MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-fable-5-1": {
        # Fable tier. Cache reads are $0.25/MTok — NOT 0.1x input.
        "input": 10.00,
        "output": 50.00,
        "cache_write": 12.50,
        "cache_read": 0.25,
    },
    "claude-fable-5": {
        "input": 10.00,
        "output": 50.00,
        "cache_write": 12.50,
        "cache_read": 1.00,
    },
    "claude-opus-5": {
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_read": 0.50,
    },
    "claude-sonnet-5": {
        "input": 2.00,
        "output": 10.00,
        "cache_write": 2.50,
        "cache_read": 0.20,
    },
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
    *,
    strict: bool = False,
) -> float:
    """Return USD cost for a single token.consumed event.

    Prices are per 1M tokens; this divides by 1_000_000 internally.

    An unpriced model yields 0.0 and logs at ERROR — $0.00 is a wrong answer,
    not a missing one, and it is invisible once summed. Pass strict=True to
    raise UnknownModelPricing instead; callers that report money to a human
    should, so a stale table fails loudly rather than under-reporting.
    """
    if not model:
        return 0.0

    normalized = _normalize_model_id(model)
    pricing = CLAUDE_MODEL_PRICING.get(normalized)

    if pricing is None:
        if strict:
            raise UnknownModelPricing(
                f"no pricing for model {model!r} (normalized {normalized!r}); "
                "add it to CLAUDE_MODEL_PRICING in core/pricing/claude_models.py"
            )
        _log.error(
            "compute_cost: unknown model %r — costing it $0.00, which UNDER-REPORTS "
            "spend. Add it to CLAUDE_MODEL_PRICING.",
            model,
        )
        return 0.0

    cost = (
        input_tokens * pricing["input"]
        + output_tokens * pricing["output"]
        + cache_creation_tokens * pricing["cache_write"]
        + cache_read_tokens * pricing["cache_read"]
    ) / 1_000_000

    return cost
