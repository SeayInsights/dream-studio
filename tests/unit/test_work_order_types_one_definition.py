"""Work-order types have one definition, and every site that spells one is a subset of it.

WHY THIS FILE EXISTS. `ds work-order create --type` said "One of the declared work-order
types" and accepted any string, filing it as `infrastructure` by default. Nothing declared
the types anywhere the CLI could ask: review_rules held ten in a private map,
brief_currency three, milestones/close two, close_main one, and the ds-project SKILL.md a
fifth copy -- the one an agent authoring a work order actually reads. Five spellings, no
owner, and the CLI could ask none of them.
"""

from __future__ import annotations

import json

import pytest

from core.gates.brief_currency import _UI_TYPES
from core.milestones.close import _UI_WO_TYPES
from core.work_orders.close_main import _VERIFY_EXEMPT_TYPES
from core.work_orders.models import WORK_ORDER_TYPES
from core.work_orders.review_rules import _TYPE_ARTIFACT


def test_the_review_map_covers_exactly_the_declared_types():
    """review_rules decides how each type is reviewed. A declared type it does not know
    would be created and then reviewed as nothing; a type it knows that is not declared
    could never be created. Both directions are checked, so the two cannot drift apart."""
    assert set(_TYPE_ARTIFACT) == set(WORK_ORDER_TYPES)


@pytest.mark.parametrize(
    "name, subset",
    [
        ("brief_currency._UI_TYPES", _UI_TYPES),
        ("milestones.close._UI_WO_TYPES", _UI_WO_TYPES),
        ("close_main._VERIFY_EXEMPT_TYPES", _VERIFY_EXEMPT_TYPES),
    ],
)
def test_every_subset_is_drawn_from_the_one_definition(name, subset):
    """The subsets are intersections with the canonical set by construction, so this holds
    structurally -- but the construction could be undone by an edit, and then a typo in a
    subset would silently invent a type again."""
    assert set(subset) <= set(WORK_ORDER_TYPES), f"{name} names a type nothing declares"
    assert subset, f"{name} intersected to nothing -- every member is misspelled"


def test_the_ui_subsets_agree_on_what_ui_means():
    """Two modules carve out the UI-bearing types for two different gates. brief_currency
    counts saas_feature (a SaaS feature ships a surface); the milestone close does not
    (it demands a CWV result, which a feature with no page cannot produce). The smaller
    must sit inside the larger, or one gate would call UI what the other calls not."""
    assert set(_UI_WO_TYPES) <= set(_UI_TYPES)


def test_the_door_refuses_an_undeclared_type(tmp_path, capsys):
    """This used to be accepted and stored. argparse's refusal names the valid choices, so
    the operator is told what exists rather than left to guess a spelling."""
    from interfaces.cli.ds import main

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--home",
                str(tmp_path),
                "work-order",
                "create",
                "p-1",
                "--title",
                "A thing",
                "--description",
                "A description long enough to pass the prompt floor for a work order, easily.",
                "--type",
                "widget",
            ]
        )
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "invalid choice: 'widget'" in err
    for declared in WORK_ORDER_TYPES:
        assert declared in err, f"the refusal does not list {declared}"


def test_create_refuses_an_undeclared_type_the_same_way_start_would():
    """The CLI door's argparse `choices=` refuses an undeclared --type before
    create_work_order() is ever reached -- but ds_work_order_create (MCP) and any other
    direct caller have no argparse layer at all, and called straight into
    create_work_order() with no check of its own. Reported directly: create accepted
    'chore' without complaint, and start then refused with "Unrecognized work order
    type: chore" -- after the work order already existed. The same "validated in only
    one of two doors" shape add_task's own admission gate had. source_root=pathlib.Path(".")
    mirrors test_an_undeclared_priority_is_refused_where_it_can_be_reported -- resolves
    to this repo's own real authority, which the check below never reaches anyway."""
    import pathlib

    from core.work_orders.mutations import create_work_order

    result = create_work_order(
        project_id="p-1",
        milestone_id="m-1",
        title="A thing",
        description="A description long enough to clear the prompt floor for a work order.",
        work_order_type="chore",
        source_root=pathlib.Path("."),
    )
    assert result["ok"] is False
    assert "chore" in result["error"], result["error"]
    for declared in WORK_ORDER_TYPES:
        assert declared in result["error"], f"the refusal does not name {declared}"


def _create_past_the_type_check(**kwargs):
    """Call create_work_order and report whether the type check itself was what
    stopped it -- regardless of what happens next (no project, no real authority in
    this test's isolated env). Everything downstream of the type check is out of
    scope here; only whether THIS check wrongly fired is."""
    import pathlib

    from core.work_orders.mutations import create_work_order

    try:
        result = create_work_order(source_root=pathlib.Path("."), **kwargs)
    except RuntimeError as exc:
        return str(exc)
    return result.get("error", "")


def test_create_does_not_refuse_any_declared_type():
    """A real, declared type must not be the reason create_work_order refuses. The type
    check runs before create_work_order needs a real project or authority (same
    positioning as the priority check it mirrors), so whatever stops the call below --
    "Project not found", or no authority in this test's isolated env -- it is never the
    type check."""
    for wo_type in WORK_ORDER_TYPES:
        error = _create_past_the_type_check(
            project_id="p-1-does-not-exist",
            milestone_id="m-1",
            title="A thing",
            description="A description long enough to clear the prompt floor for a work order.",
            work_order_type=wo_type,
        )
        assert (
            "is not one the platform declares" not in error
        ), f"{wo_type} was refused by the type check: {error}"


def test_create_does_not_refuse_an_absent_type():
    """work_order_type=None is a different, already-handled question (start_brief.py's
    own "Work order has no type assigned") -- this check must not turn that into the
    'unrecognized type' refusal too."""
    error = _create_past_the_type_check(
        project_id="p-1-does-not-exist",
        milestone_id="m-1",
        title="A thing",
        description="A description long enough to clear the prompt floor for a work order.",
        work_order_type=None,
    )
    assert "is not one the platform declares" not in error


def test_no_module_carries_a_second_full_list():
    """A second copy of all ten anywhere in core/ or interfaces/ is the thing this file
    exists to end. The subsets are allowed; a full list is not."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    full = set(WORK_ORDER_TYPES)
    offenders = []
    for py in list((repo / "core").rglob("*.py")) + list((repo / "interfaces").rglob("*.py")):
        if py.name == "models.py" and py.parent.name == "work_orders":
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        # Only a literal list of ALL ten counts; review_rules' map is keyed by them and is
        # the legitimate consumer that must name each one.
        if py.name == "review_rules.py":
            continue
        if all(f'"{t}"' in text for t in full):
            offenders.append(str(py.relative_to(repo)))
    assert offenders == [], f"a second full copy of the type list: {offenders}"


def test_the_declared_types_are_what_the_help_text_promises():
    """`--type` help says "One of the declared work-order types". The parser's choices are
    now exactly those types, so the sentence is true rather than aspirational. Reads the
    real tree via build_parser, the door tests/unit/test_every_help_renders.py walks."""
    from interfaces.cli.ds import build_parser

    parser = build_parser()
    sub = next(a for a in parser._actions if a.dest == "command")
    wo = sub.choices["work-order"]
    wo_sub = next(a for a in wo._actions if getattr(a, "choices", None) and "create" in a.choices)
    create = wo_sub.choices["create"]
    type_action = next(a for a in create._actions if a.dest == "work_order_type")
    assert tuple(type_action.choices) == WORK_ORDER_TYPES
    assert type_action.default in WORK_ORDER_TYPES


def test_the_authoring_skill_lists_exactly_the_declared_types():
    """The copy an agent reads when it authors a work order.

    canonical/skills/ds-project/SKILL.md carries a table of the valid types with a
    sentence explaining each. It agrees with models.py today, and nothing checked that it
    did -- an agent choosing a type reads the table, and the door now refuses anything the
    tuple does not hold, so a drifted row would be an instruction to invoke a refusal.
    The table earns its place by explaining WHEN to use each type; only the set is pinned.
    """
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    skill = repo / "canonical" / "skills" / "ds-project" / "SKILL.md"
    if not skill.is_file():
        pytest.skip("the ds-project pack has been dissolved; the table went with it")
    block = skill.read_text(encoding="utf-8")
    start = block.index("### Valid Work Order Types")
    block = block[start:]
    if "\n## " in block:
        block = block[: block.index("\n## ")]
    listed = set(re.findall(r"^\| `([a-z_]+)` \|", block, re.M))
    assert listed == set(WORK_ORDER_TYPES)


def test_the_baseline_migration_seeds_exactly_the_declared_types():
    """The seventh site, and the load-bearing one.

    `business_work_order_types` is not a mirror of the tuple: each row carries that type's
    pre_build_gate, post_build_gate, build_executor and precondition_skill, and
    `run_gate_check` reads them when a work order closes. A declared type with no row is a
    work order that can be created and then started against nothing; a row with no
    declared type is a set of gates nothing can reach, which is the shape rule 18 of the
    ds-workorder pack exists to refuse one level up.

    Read from the migration, not from a live authority, so the answer does not depend on
    whose database is at hand.
    """
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    sql = (repo / "core" / "event_store" / "migrations" / "142_lean_baseline.sql").read_text(
        encoding="utf-8"
    )
    start = sql.index("INSERT OR IGNORE INTO business_work_order_types")
    end = sql.index(";", start)
    block = sql[start:end]
    seeded = set(re.findall(r"^\s*\('([a-z_]+)',", block, re.M))
    assert seeded == set(WORK_ORDER_TYPES), (
        "the tuple and the seeded type rows disagree; a type with no row cannot be started, "
        f"a row with no type is unreachable. only-seeded={sorted(seeded - set(WORK_ORDER_TYPES))} "
        f"only-declared={sorted(set(WORK_ORDER_TYPES) - seeded)}"
    )
