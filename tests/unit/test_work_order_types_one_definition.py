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
    block = block[block.index("### Valid Work Order Types") :]
    if "
## " in block:
        block = block[: block.index("
## ")]
    listed = set(re.findall(r"^\| `([a-z_]+)` \|", block, re.M))
    assert listed == set(WORK_ORDER_TYPES)
