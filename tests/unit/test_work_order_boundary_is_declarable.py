"""A module boundary must be declarable, stored, and readable by the thing that reads it.

Operator, on the substrate: rules are "a lot of prose laid on top of each other as
suggestions with no rules, evals, or really any real test that doing anything they are
supposed to". `Module boundary:` was the proof. It is load-bearing -- edit attribution
matches against it, and without a match the stop hook falls back to the most recently
started work order, stamping every edit in a project with it regardless of subject. The
operator hit that whenever they switched projects and had to bypass enforcement to end a
session.

Three things were true at once:

* No CLI argument produced the clause. Authors were expected to remember a literal
  documented in no skill, no help text, and no template.
* `create_work_order` accepted `--description` and DROPPED it. The emitter never put it in
  the event payload and the projection never read it. Measured on the live authority: 443
  of 920 work orders with an empty description, and 18 of the 19 created since
  2026-09-01.
* So a boundary could not be declared through the CLI at all. 0 of 25 in-progress work
  orders had one -- not because authors forgot, but because it was impossible.

A rule whose input cannot be supplied is not a rule. These tests run the REAL parser over
the REAL composer's output, and drive the REAL emitter through the REAL projection, so a
regression anywhere in that chain fails here rather than degrading into a guess in
production.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from core.work_orders.mutations import compose_module_boundary

REPO_ROOT = Path(__file__).resolve().parents[2]
ENFORCEMENT_PATH = REPO_ROOT / "runtime" / "lib" / "enforcement.py"


def _real_parser():
    """The actual consumer, loaded by path.

    Never a local copy of its regex: a duplicated rule drifts from the original, and this
    whole file exists because a producer and a consumer disagreed about a format.
    """
    spec = importlib.util.spec_from_file_location("enforcement_under_test", ENFORCEMENT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_composed_boundary_round_trips_through_the_real_parser() -> None:
    """The producer must emit exactly what the consumer parses."""
    parser = _real_parser()
    described = compose_module_boundary(
        "Fix the drift check.", ["interfaces/cli/commands", "core/work_orders"]
    )

    assert parser.boundary_globs(described) == ["interfaces/cli/commands", "core/work_orders"]


def test_a_comma_separated_string_works_too() -> None:
    """Both shapes an author or a caller would naturally pass."""
    parser = _real_parser()
    described = compose_module_boundary("x", "core/gates, tests/unit")

    assert parser.boundary_globs(described) == ["core/gates", "tests/unit"]


def test_a_boundary_the_parser_would_discard_is_not_stored() -> None:
    """Refuse to store something that would look declared and match nothing.

    ``boundary_globs`` keeps only parts containing ``/`` or ``.``. Storing a clause it
    discards is worse than storing none: the work order then appears to declare a boundary
    while matching no path, which is the silent-wrong-answer shape this repo keeps finding.
    """
    parser = _real_parser()
    described = compose_module_boundary("x", ["nonsense", "alsobad"])

    assert described == "x", "an unparseable boundary must not be written into the description"
    assert parser.boundary_globs(described) == []


def test_a_hand_written_clause_is_left_alone() -> None:
    """An author who wrote the clause themselves is not second-guessed or duplicated."""
    existing = "Scope. Module boundary: core/a, core/b."
    assert compose_module_boundary(existing, ["core/c"]) == existing


def test_no_boundary_leaves_the_description_untouched() -> None:
    """The composer must not invent a boundary that was never supplied."""
    assert compose_module_boundary("just a description", None) == "just a description"
    assert compose_module_boundary("just a description", []) == "just a description"


def test_the_create_door_requires_a_boundary() -> None:
    """`ds work-order create` must REFUSE without one.

    This is what turns the rule from a suggestion into a rule: the door will not mint a
    work order whose edits cannot be attributed. Asserted against the real parser
    definition rather than by running the CLI, so it holds in a checkout with no authority
    database.
    """
    import argparse

    from interfaces.cli.commands.work_order_dispatch import register

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    register(sub)

    work_order = sub.choices.get("work-order")
    assert work_order is not None, "the work-order command group disappeared"
    create = None
    for sub_action in work_order._subparsers._group_actions:  # noqa: SLF001
        create = sub_action.choices.get("create")
        if create is not None:
            break
    assert create is not None, "the create subcommand disappeared"

    boundary = [
        a
        for a in create._actions  # noqa: SLF001
        if "--module-boundary" in (a.option_strings or [])
    ]
    assert boundary, "create must expose --module-boundary"
    assert boundary[0].required, (
        "--module-boundary must be REQUIRED. Optional means it will be omitted, which is "
        "how 0 of 25 in-progress work orders ended up with no boundary and every edit was "
        "attributed by recency."
    )


def test_the_projection_materializes_the_description() -> None:
    """Superseded by a behavioural check; kept only as a pointer.

    This used to assert that certain SOURCE TEXT appeared in the projection and the
    emitter. That proves a string is present, not that a value survives -- it would pass
    against a projection whose INSERT dropped the column, and it said nothing about the
    next field someone added. The real round trip now runs the emitter's payload key set
    through the real projection into a real bootstrapped schema, in
    tests/unit/test_seam_payload_to_projection.py, and fails when ANY payload key goes
    unaccounted for rather than just this one.
    """
    seam = REPO_ROOT / "tests" / "unit" / "test_seam_payload_to_projection.py"
    assert seam.is_file(), (
        "the behavioural seam contract is gone; description persistence is unverified "
        "again -- restore tests/unit/test_seam_payload_to_projection.py"
    )
