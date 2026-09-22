"""A milestone must carry the prompt its work orders answer to.

The hierarchy is a prompt chain: a task is a specific instruction, a work order
is the goal those instructions add up to, a milestone is the goal those work
orders add up to. A milestone with only a title gives every work order beneath it
nothing to derive its own goal from.

This is the milestone half of the same rule `test_work_order_prompt_required.py`
covers one layer down. Measured on the authority 2026-09-21: 8 of 97 milestones
had no description at all.

The floor is measured, not chosen. Of the 89 milestones that DO carry one, the
two shortest are both the literal string "probe" from test fixtures; the shortest
real description is 54 characters ("Operator-owned security actions surfaced by
the audit."). 50 refuses the probes and admits every genuine description,
including the terse ones -- which is the point of a floor rather than a rubric.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.milestones.mutations import _MIN_DESCRIPTION_CHARS, create_milestone

GOOD = "Wire the DuckDB analytics projection so the dashboard has a data source at all."


def _create(description, **kw):
    """The description check runs before any database access, so no fixture is
    needed: a refusal returns before `_require_db` is reached."""
    return create_milestone(
        project_id="p-1",
        title="A title",
        description=description,
        source_root=Path("."),
        **kw,
    )


@pytest.mark.parametrize(
    "description,why",
    [
        ("", "empty string -- the 8-of-97 case"),
        (None, "None, which is what the CLI passed when the flag was omitted"),
        ("   \n\t ", "whitespace only"),
        ("probe", "the literal fixture string that is the only thing below the floor"),
        ("Security work", "a phrase, not a prompt"),
    ],
)
def test_a_milestone_without_a_prompt_is_refused(description, why):
    result = _create(description)
    assert result["ok"] is False, why
    assert "description is required" in result["error"]


def test_the_error_names_the_floor_and_what_was_given():
    """A refusal that does not say how to satisfy it is a wall."""
    result = _create("too short")
    assert str(_MIN_DESCRIPTION_CHARS) in result["error"]
    assert "got 9" in result["error"]


def test_a_real_prompt_passes_the_check():
    """It must get PAST the description gate. What happens after is not this
    test's business and is not stable -- run alone there is no authority and
    `_require_db` raises, while under the full suite conftest has stood one up."""
    try:
        result = _create(GOOD)
    except RuntimeError:
        return  # reached the database layer, which is the point
    if result.get("ok") is False:
        assert "description is required" not in result["error"]


def test_the_floor_admits_the_shortest_real_description():
    """54 characters is the shortest genuine milestone description on the
    authority. A floor above it would start refusing work people actually wrote,
    which is how a floor turns into a rubric."""
    assert _MIN_DESCRIPTION_CHARS <= 54
    shortest_real = "Operator-owned security actions surfaced by the audit."
    assert len(shortest_real) >= _MIN_DESCRIPTION_CHARS


def test_the_cli_requires_it_too():
    """A rule the mutation enforces and the CLI does not expose is a rule nothing
    can obey -- `--description` defaulted to "" until 2026-09-21, so every CLI
    milestone was created promptless without anyone being told."""
    import argparse

    from interfaces.cli.commands.milestone import register  # type: ignore[attr-defined]

    parser = argparse.ArgumentParser()
    register(parser.add_subparsers(dest="cmd"))
    with pytest.raises(SystemExit):
        parser.parse_args(["milestone", "create", "p-1", "--title", "T"])
