"""The pricing table must carry rates for every model actually in use.

History — this has now failed twice, the same way both times:

  1. WO-COST-MODEL-RATES: claude-opus-4-8 shipped, was absent from
     CLAUDE_MODEL_PRICING, compute_cost logged "unknown model -> 0.0", and all
     Opus usage costed $0. Fixed by adding the model, and guarded by a test
     that pinned a hardcoded CURRENT_MODELS tuple.

  2. The 5-series rollover (opus-5 / sonnet-5 / fable-5). The hardcoded tuple
     still named the 4-series, so it still passed — while 99.2% of 65,590
     recorded token events priced at $0.00 for four months.

The lesson is that a hardcoded list of "current" models guards the models that
were current on the day it was written. It is a snapshot, not a policy. So the
guard below derives what to check from evidence instead:

  * test_models_with_recorded_usage_are_priced reads the model_ids that the
    event store has actually recorded and requires each to price. This is the
    guard that would have caught both regressions on the day they happened.
  * test_models_referenced_in_source_are_priced scans first-party source for
    model-id literals, so a fresh checkout with no telemetry is still covered.

Neither test needs editing when a new model ships.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from core.pricing.claude_models import (
    CLAUDE_MODEL_PRICING,
    UnknownModelPricing,
    _normalize_model_id,
    compute_cost,
)

REPO_ROOT = Path(__file__).parents[2]


def _is_priced(model: str) -> bool:
    """True when `model` has a rate in the table (date suffixes normalized).

    LIVES HERE, NOT IN THE PRICING MODULE. It was written there as a public
    helper and nothing in production ever called it -- `compute_cost` does its
    own lookup, and the dashboard-truth invariant does the same test in DuckDB
    SQL because it runs inside the query. A predicate only the tests ask for is
    the tests' own, and the reachability gate is right to refuse it upstream.
    """
    return bool(model) and _normalize_model_id(model) in CLAUDE_MODEL_PRICING


# A Claude model id: family + version. Deliberately narrower than "claude-*",
# which also matches adapter ids like "claude-code" and "claude-cli".
_MODEL_ID_RE = re.compile(
    r"\bclaude-(?:opus|sonnet|haiku|fable|mythos)-[0-9][0-9a-z-]*", re.IGNORECASE
)

# Ids that appear in source as deliberate negatives or historical references,
# and must NOT be required to price.
_NOT_REAL_MODELS = frozenset(
    {
        "claude-opus-4-5-20251101",  # Vertex @-separator doc example
    }
)


def _first_party_sources() -> list[Path]:
    """Repo source files that may name a model id, excluding test fixtures."""
    out: list[Path] = []
    for sub in ("core", "projections", "interfaces", "control", "config", "canonical"):
        root = REPO_ROOT / sub
        if not root.is_dir():
            continue
        for p in root.rglob("*.py"):
            if "worktrees" in p.parts or "__pycache__" in p.parts:
                continue
            out.append(p)
    return out


# --------------------------------------------------------------------------
# The evidence-derived guards. These are the ones that matter.
# --------------------------------------------------------------------------


# NO LIVE-EVENT-STORE TEST LIVES HERE, AND ONE USED TO. It asked the real authority
# for every model with recorded token usage and required each to be priced -- the
# regression that shipped twice. It could never once have run: tests/conftest.py
# redirects DREAM_STUDIO_DB_PATH to an empty per-session temp store before any test
# imports, so `db_path()` inside pytest resolves to a database with no token.consumed
# rows and the guard skipped itself every time. A skip is not a pass, but it reads like
# one in a green summary, which is the same look-away-and-it-agrees shape the pricing
# table's own silence had.
#
# The assertion was not dropped, it was moved to where it can see the data: the
# `token_models_are_priced` invariant in core/gates/dashboard_truth.py, which runs
# against the operator's real store as a gate rather than a unit test. Reaching around
# the conftest redirect to restore it here would put live operator state back inside a
# unit test, which the test-isolation gate exists to forbid.


def test_models_referenced_in_source_are_priced():
    """Any model id hardcoded in first-party source must have a rate.

    Covers a fresh checkout / CI, where there is no telemetry to derive from.
    """
    found: dict[str, list[str]] = {}
    for path in _first_party_sources():
        try:
            src = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for raw in _MODEL_ID_RE.findall(src):
            model = raw.lower()
            if model in _NOT_REAL_MODELS:
                continue
            found.setdefault(model, []).append(str(path.relative_to(REPO_ROOT)))

    assert found, "model-id scan found nothing — the regex has drifted"

    unpriced = {m: sorted(set(v)) for m, v in found.items() if not _is_priced(m)}
    assert not unpriced, (
        f"model ids are hardcoded in source but unpriced: {unpriced}. "
        "Either add the rate or stop naming the model."
    )


# --------------------------------------------------------------------------
# Behavioural contract of compute_cost itself.
# --------------------------------------------------------------------------


def test_unpriced_model_costs_zero_but_logs_an_error():
    """$0.00 for an unknown model is a wrong answer, so it must be loud."""
    with caplog_at_error() as caplog:
        cost = compute_cost("claude-not-a-real-model-9", 1_000_000, 1_000_000)
    assert cost == 0.0
    assert "unknown model" in caplog.text.lower()
    assert caplog.records and caplog.records[-1].levelno >= logging.ERROR, (
        "an unpriced model must log at ERROR — a WARNING for this went unread "
        "for four months while the cost panel reported 0.8% of reality"
    )


def test_strict_mode_raises_instead_of_under_reporting():
    """Callers that report money to a human opt into failing loudly."""
    with pytest.raises(UnknownModelPricing):
        compute_cost("claude-not-a-real-model-9", 1000, 1000, strict=True)
    # A priced model is unaffected by strict.
    assert compute_cost("claude-opus-5", 1_000_000, 0, strict=True) == 5.0


def test_date_suffixes_normalize_to_the_base_rate():
    assert compute_cost("claude-opus-5-20260401", 1_000_000, 0) == 5.0
    assert compute_cost("claude-haiku-4-5-20251001", 1_000_000, 0) == 1.0


def test_opus_4_8_still_priced():
    """Direct regression guard for WO-COST-MODEL-RATES."""
    assert "claude-opus-4-8" in CLAUDE_MODEL_PRICING
    assert compute_cost("claude-opus-4-8", 1_000_000, 1_000_000) == 30.0


def test_cache_read_is_not_derived_from_input():
    """Fable 5.1 prices cache reads below the usual 0.1x — it is published, not derived."""
    fable = CLAUDE_MODEL_PRICING["claude-fable-5-1"]
    assert fable["cache_read"] == 0.25
    assert (
        fable["cache_read"] != fable["input"] * 0.1
    ), "cache_read must come from the published rate card, not from a ratio"


def test_every_entry_has_all_four_rates():
    required = {"input", "output", "cache_write", "cache_read"}
    for model, rates in CLAUDE_MODEL_PRICING.items():
        assert required <= set(rates), f"{model} is missing {required - set(rates)}"
        for key, value in rates.items():
            assert isinstance(value, (int, float)) and value > 0, f"{model}.{key} = {value!r}"


def test_normalizer_leaves_undated_ids_alone():
    assert _normalize_model_id("claude-sonnet-5") == "claude-sonnet-5"
    assert _normalize_model_id("  CLAUDE-OPUS-5  ") == "claude-opus-5"


# --------------------------------------------------------------------------
# Consumers must not carry private rate tables (that is how #1 happened).
# --------------------------------------------------------------------------


def test_no_consumer_defines_its_own_rate_table():
    consumers = (
        "projections/core/cost_analysis.py",
        "projections/api/queries/token_attribution.py",
        "interfaces/cli/efficiency_analytics.py",
    )
    for rel in consumers:
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert (
            "claude_models" in src or "compute_cost" in src
        ), f"{rel} should source rates from core.pricing.claude_models"
        assert not re.search(r"(?<!CLAUDE_)\bMODEL_PRICING\s*[:=]", src), (
            f"{rel} must not define a private MODEL_PRICING table — a second "
            "table drifts from canon, which is how the opus-4-8 miss happened"
        )


def test_a_consumer_prices_a_current_model_end_to_end():
    """Exercise a real consumer, not just the table."""
    from interfaces.cli.efficiency_analytics import compute_cost_analysis

    result = compute_cost_analysis(
        [
            {
                "session_id": "s-1",
                "primary_model": "claude-opus-5",
                "prompt_tokens": 1_000_000,
                "completion_tokens": 1_000_000,
                "date": "2026-09-17",
            }
        ],
        total_tasks=0,
    )
    assert result["total_cost_usd"] == 30.0, (
        f"efficiency_analytics must price opus-5 through the shared table, "
        f"got {result['total_cost_usd']}"
    )


# Small helper so the ERROR-level assertion reads cleanly above.
def caplog_at_error():
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        handler = _ListHandler()
        logger = logging.getLogger("core.pricing.claude_models")
        prev_level, prev_prop = logger.level, logger.propagate
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        try:
            yield handler
        finally:
            logger.removeHandler(handler)
            logger.setLevel(prev_level)
            logger.propagate = prev_prop

    return _ctx()


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    @property
    def text(self) -> str:
        return "\n".join(r.getMessage() for r in self.records)
