"""A work order must carry the prompt the tasks under it answer to.

Dream Studio's hierarchy is a prompt chain: a task is a specific instruction, a
work order is the goal those instructions add up to, a milestone is the goal
those work orders add up to. A work order with only a title breaks that chain in
the middle, and the task then has to re-derive an intent nobody wrote down.

Measured on the authority 2026-09-21 -- 446 of 1,038 work orders had no
description at all, and outside this repo it ran far worse:

    Attune                    0% empty     the one project filled at every layer
    Fulcrum                  78% empty
    Driver's License         91% empty
    DreamySuite              95% empty
    Dream Command           100% empty
    Dream Studio (self)      30% empty

The difference between Attune and the rest is not discipline. It is that nothing
ever asked.

The floor is measured, not chosen: of the 592 work orders that DO carry a
description the shortest is 81 characters, so 60 refuses none of them. It is a
floor and not a rubric on purpose -- a check that graded prompt quality would be
arguing with the author, and this only refuses an absence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.work_orders.mutations import _MIN_DESCRIPTION_CHARS, create_work_order

# Long enough to clear the floor, and a realistic shape: what and why.
GOOD = (
    "Carry the attribution the emitter already resolved into events_fact, so cost "
    "per work order stops reading zero on the dashboard."
)


def _create(description, **kw):
    """The description check runs before any database access, so no fixture is
    needed: a refusal returns before `_require_db` is ever called."""
    return create_work_order(
        project_id="p-1",
        milestone_id="m-1",
        title="A title",
        description=description,
        source_root=Path("."),
        **kw,
    )


@pytest.mark.parametrize(
    "description,why",
    [
        ("", "empty string -- the 446-work-order case"),
        (None, "None, which is what the CLI passes when the flag is omitted"),
        ("   \n\t  ", "whitespace only"),
        ("Fix the thing", "a short phrase, not a prompt"),
        ("A title", "the title pasted into the description field"),
    ],
)
def test_a_work_order_without_a_prompt_is_refused(description, why):
    result = _create(description)
    assert result["ok"] is False, why
    assert "description is required" in result["error"]


def test_the_error_says_what_is_wanted_and_by_how_much():
    """A refusal that does not say how to satisfy it is a wall. The message names
    the floor and what was actually supplied."""
    result = _create("too short")
    assert str(_MIN_DESCRIPTION_CHARS) in result["error"]
    assert "got 9" in result["error"]


def test_a_real_prompt_passes_the_check():
    """It must get PAST the description gate.

    What happens after is not this test's business and is not stable: run alone
    there is no authority and `_require_db` raises, while under the full suite
    conftest has stood up a temp database and the call proceeds. Asserting either
    one would make this test fail depending on what else ran, so it asserts the
    only thing it is about -- that the refusal, if any, is not about the
    description.
    """
    try:
        result = _create(GOOD)
    except RuntimeError:
        return  # reached the database layer; past validation, which is the point
    if result.get("ok") is False:
        assert "description is required" not in result["error"]


def test_the_floor_refuses_none_of_the_real_descriptions():
    """The floor is derived from the corpus it has to admit. The shortest real
    description on the authority is 81 characters; a floor above that would start
    refusing work orders people actually wrote."""
    assert _MIN_DESCRIPTION_CHARS < 81


def test_the_module_boundary_does_not_count_toward_the_floor():
    """`module_boundary` is composed INTO the description afterwards. If it counted,
    passing a long enough path list would satisfy the prompt requirement with no
    prompt -- exactly the absence this refuses."""
    result = _create(
        "short",
        module_boundary=["core/a/very/long/path/that/is/easily/sixty/characters/wide.py"],
    )
    assert result["ok"] is False
    assert "description is required" in result["error"]
    assert "does not count" in result["error"]
