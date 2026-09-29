"""Selecting a subset of the round table's compiled reviewers by name.

`resolve_agent_names` is what makes a genuinely mixed roster (nine seats on one tool,
one on another) reachable through `ds integrate install <tool> --agents ...` instead of
every target getting the whole bench or nothing -- the gap an operator hit directly
after the per-tool model work shipped: installing codex and gemini_cli both gave all
nine reviewers to each, with no way to split them.

Every call here omits `repo_root` on purpose: this file is Dream Studio's own bench
only. A project's own seat becoming resolvable too (same function, `repo_root` given)
has its own tests alongside the installers that consume it -- see
test_specialist_agents_install.py and test_specialist_agents_codex_install.py.
"""

from __future__ import annotations

import pytest

from integrations.compiler.reviewers import reviewer_files, seat_names
from integrations.compiler.reviewers import resolve_agent_names


def test_resolves_by_agent_slug():
    resolved = resolve_agent_names(["review-finding-integrity"])
    assert [p.stem for p in resolved] == ["review-finding-integrity"]


def test_resolves_by_seat_name():
    resolved = resolve_agent_names(["Finding integrity"])
    assert [p.stem for p in resolved] == ["review-finding-integrity"]


def test_a_slug_and_the_seat_name_that_derives_it_resolve_the_same_file():
    by_slug = resolve_agent_names(["review-finding-integrity"])
    by_seat = resolve_agent_names(["Finding integrity"])
    assert by_slug == by_seat


def test_preserves_requested_order_not_sorted_order():
    seats = seat_names()  # alphabetical, so reversing it is guaranteed out of order
    assert len(seats) >= 2, "need at least two seats for an order-preservation check"
    requested = list(reversed(seats))
    resolved = resolve_agent_names(requested)
    expected = [resolve_agent_names([s])[0].stem for s in requested]
    assert [r.stem for r in resolved] == expected
    assert [r.stem for r in resolved] != sorted(r.stem for r in resolved)


def test_deduplicates_a_name_and_its_slug_requested_together():
    resolved = resolve_agent_names(["Finding integrity", "review-finding-integrity"])
    assert len(resolved) == 1


def test_empty_list_resolves_to_nothing():
    assert resolve_agent_names([]) == []


def test_unknown_name_raises_naming_both_valid_sets():
    with pytest.raises(ValueError) as exc_info:
        resolve_agent_names(["not a real seat or slug"])
    message = str(exc_info.value)
    assert "not a real seat or slug" in message
    assert "review-finding-integrity" in message  # a real slug, named as valid
    assert "Finding integrity" in message  # a real seat name, named as valid


def test_one_unknown_name_among_valid_ones_still_raises():
    """Partial success is not success: installing 8 of 9 requested reviewers because
    the 9th name was mistyped should fail loudly, not silently ship a short roster."""
    with pytest.raises(ValueError, match="unknown"):
        resolve_agent_names(["Finding integrity", "Not A Seat"])


def test_covers_every_real_reviewer_file():
    """Guard the guard: every compiled reviewer must be reachable by its own slug, or
    the whole selection mechanism is untestable against the real bench."""
    for path in reviewer_files():
        resolved = resolve_agent_names([path.stem])
        assert resolved == [path]
