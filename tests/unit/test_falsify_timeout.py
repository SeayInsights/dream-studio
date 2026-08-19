"""WO-FALSIFY-TIMEOUT: the falsification role needs a budget it can finish in.

Discovered on the falsification pass's FIRST live run: the grader timed out at
the shared 360s on an ordinary multi-file diff. The unavailable path handled it
correctly (recorded, no false-fail), but a grader that cannot finish on realistic
input is dead capability exactly where the worst cases matter most. Two levers:
a longer per-role window, and not handing it unbounded input.
"""

from __future__ import annotations

from core.work_orders.verify_graders import (
    _DEFAULT_COLLECT_TIMEOUT,
    role_collect_timeout,
    role_retry_timeout,
)
from core.work_orders.verify_main import _FALSIFICATION_DIFF_BUDGET, budget_falsification_diff


def test_falsification_gets_longer_timeout():
    """The whole-diff role gets a bigger window than the narrow-scope roles, and
    the budgets are named constants rather than magic numbers at the call site."""
    assert role_collect_timeout("falsification") > _DEFAULT_COLLECT_TIMEOUT
    for narrow in ("completion", "correctness", "quality", "migration"):
        assert role_collect_timeout(narrow) == _DEFAULT_COLLECT_TIMEOUT
    # An unknown/None role falls back to the default rather than raising.
    assert role_collect_timeout(None) == _DEFAULT_COLLECT_TIMEOUT
    assert role_collect_timeout("nonexistent") == _DEFAULT_COLLECT_TIMEOUT
    # The retry window is per-role too, so a falsification retry can also finish.
    assert role_retry_timeout("falsification") > role_retry_timeout("completion")


def _commit(sha: str, size: int) -> str:
    return f"=== commit {sha} ===\n" + ("+x\n" * (size // 3))


def test_large_diff_is_budgeted_and_marked():
    """A diff over budget is trimmed to whole newest-first commit sections, kept
    in chronological order, and reported as truncated."""
    small = _commit("aaa1111", 100)
    assert budget_falsification_diff(small) == (small, False)

    oldest = _commit("old00001", 40_000)
    middle = _commit("mid00002", 40_000)
    newest = _commit("new00003", 40_000)
    big = oldest + middle + newest
    assert len(big) > _FALSIFICATION_DIFF_BUDGET

    trimmed, truncated = budget_falsification_diff(big)
    assert truncated is True
    assert len(trimmed) <= len(big)
    # Newest kept, oldest dropped — the operator is declaring the newest work done.
    assert "new00003" in trimmed
    assert "old00001" not in trimmed
    # Whole sections only: no half-commit fragments.
    assert trimmed.startswith("=== commit ")
    # Chronological order restored for the reader (mid before new).
    if "mid00002" in trimmed:
        assert trimmed.index("mid00002") < trimmed.index("new00003")


def test_budget_keeps_at_least_one_section_and_handles_markerless_diffs():
    """A single oversized commit still yields content (never an empty prompt), and
    marker-less evidence text head-truncates rather than crashing."""
    one_huge = _commit("huge0001", _FALSIFICATION_DIFF_BUDGET * 2)
    trimmed, truncated = budget_falsification_diff(one_huge)
    assert truncated is True
    assert trimmed, "a single oversized section must still produce input"
    assert "huge0001" in trimmed

    markerless = "authority evidence: " + ("y" * (_FALSIFICATION_DIFF_BUDGET + 500))
    trimmed, truncated = budget_falsification_diff(markerless)
    assert truncated is True
    assert len(trimmed) == _FALSIFICATION_DIFF_BUDGET


def test_remediation_evidence_sections_are_budgeted_too():
    """Closed-child remediation evidence (WO-GAP-EVIDENCE) uses its own header and
    must participate in the same whole-section budgeting — as whole sections, and
    behind the WO's own commits.

    This test originally asserted the evidence section survived truncation. It did,
    but only because a plain newest-first walk kept the LAST section, and evidence
    is appended after the commits — so the WO's own diff was what got dropped. The
    falsification analyst named that (empty_absent_state on this function): the
    analyst would enumerate worst cases for a change set whose diff it never saw.
    Commits are now budgeted first; the invariant kept here is the one that was
    always intended — evidence is budgeted, not exempt, and never fragmented. See
    tests/unit/test_falsification_adversarial.py for the priority itself.
    """
    parent = _commit("par00001", 40_000)
    child = "=== remediation evidence (closed gap WO abc) ===\n" + ("+fix\n" * 12_000)
    trimmed, truncated = budget_falsification_diff(parent + child)
    assert truncated is True
    assert "par00001" in trimmed, "the WO's own commit outranks appended evidence"
    assert len(trimmed) <= _FALSIFICATION_DIFF_BUDGET
    assert trimmed.lstrip().startswith("=== ")
    # Whole sections only — evidence is either included entirely or not at all.
    if "remediation evidence" in trimmed:
        assert trimmed.count("+fix\n") == 12_000
