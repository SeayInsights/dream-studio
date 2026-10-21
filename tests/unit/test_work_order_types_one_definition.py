"""Work-order types have one definition, the type registry, and every site that spells one reads it.

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

from core.work_orders import type_registry
from core.work_orders.type_registry import builtin_work_order_type_names, work_order_type_names

# The declared set, read once. No test here registers a type; the ones that do (in
# test_work_order_type_registry.py) restore the registry themselves.
BUILTIN_TYPES = builtin_work_order_type_names()


def test_every_declared_type_reviews_as_a_known_artifact_class():
    """review_rules decides how each type is reviewed from the registry. A declared type
    with no class would be created and then reviewed as nothing; registration refuses an
    unknown class, and this pins that the built-ins all carry one."""
    for declared in work_order_type_names():
        assert type_registry.artifact_class_for(declared) in type_registry.ARTIFACT_CLASSES


def test_the_ui_subsets_agree_on_what_ui_means():
    """Two gates carve out the UI-bearing types. brief_currency counts saas_feature (a SaaS
    feature ships a surface); the milestone close does not (it demands a CWV result, which
    a feature with no page cannot produce). The smaller must sit inside the larger, or one
    gate would call UI what the other calls not."""
    ui = {t for t in work_order_type_names() if type_registry.is_ui_bearing(t)}
    stales = set(type_registry.design_brief_staling_types())
    assert ui and ui <= stales


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
    for declared in work_order_type_names():
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
    for declared in work_order_type_names():
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
    for wo_type in work_order_type_names():
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


#: There is no exempt file and no exempt assignment. integrations/compiler/agents_md.py held the
#: last copy (names, descriptions and presentation order for the generated operator AGENTS.md)
#: until the registry took the descriptions and the order and the table was generated from it.
#: A list planted back there, or anywhere else, is a failure of the scan below.

#: How many declared names in ONE literal make it a second list. All ten is a copy; so is
#: nine with one left out, which is the first thing anyone would do to dodge an exact match.
_SECOND_LIST_THRESHOLD = 6

_SPLIT_METHODS = frozenset({"split", "rsplit", "splitlines"})


def second_list_lines(source: str) -> list[int]:
    """Line numbers of every literal in ``source`` that spells out most of the built-in types.

    Parsed, not grepped. A text match on `"name"` missed single-quoted lists, a list built as
    `"a b c".split()`, and anything in a file exempted wholesale. Here a literal collection
    (list, tuple, set, dict keys, or a tuple of pairs) or a `"..."`-literal `.split()` counts
    when it holds ``_SECOND_LIST_THRESHOLD`` or more of the built-in names, whatever the
    quoting. The BUILT-INS, not the live registry: a pack-declared type is not a copy of them.
    """
    import ast
    import re

    declared = set(BUILTIN_TYPES)
    tree = ast.parse(source)
    hits: list[int] = []
    for node in ast.walk(tree):
        spelled: set[str] = set()
        if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            spelled = {
                sub.value
                for sub in ast.walk(node)
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
            }
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _SPLIT_METHODS
            and isinstance(node.func.value, ast.Constant)
            and isinstance(node.func.value.value, str)
        ):
            spelled = set(re.split(r"[\s,|;]+", node.func.value.value))
        if len(spelled & declared) >= _SECOND_LIST_THRESHOLD:
            hits.append(node.lineno)
    return hits


def _modules_naming_most_declared_types() -> dict[str, list[int]]:
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    found: dict[str, list[int]] = {}
    for root in ("core", "interfaces", "integrations"):
        for py in (repo / root).rglob("*.py"):
            if py.name == "type_registry.py" and py.parent.name == "work_orders":
                continue
            rel = py.relative_to(repo).as_posix()
            source = py.read_text(encoding="utf-8", errors="replace")
            try:
                lines = second_list_lines(source)
            except SyntaxError:
                continue
            if lines:
                found[rel] = lines
    return found


def test_no_module_carries_a_second_full_list():
    """A second copy of the type list anywhere in core/, interfaces/ or integrations/ is the
    thing this file exists to end. Only the registry may name them, and there is no exemption:
    the generated AGENTS.md table, the last copy, now reads the registry."""
    offenders = _modules_naming_most_declared_types()
    assert offenders == {}, f"a second copy of the type list: {offenders}"


_SINGLE = ", ".join(repr(t) for t in BUILTIN_TYPES)
_DOUBLE = ", ".join(f'"{t}"' for t in BUILTIN_TYPES)


@pytest.mark.parametrize(
    "planted",
    [
        pytest.param(f"X = [{_DOUBLE}]", id="double-quoted-list"),
        pytest.param(f"X = [{_SINGLE}]", id="single-quoted-list"),
        pytest.param(f"X = ({_SINGLE},)", id="tuple"),
        pytest.param(f"X = {{{_SINGLE}}}", id="set"),
        pytest.param("X = {" + ", ".join(f"{t!r}: 1" for t in BUILTIN_TYPES) + "}", id="dict"),
        pytest.param(f"X = {' '.join(BUILTIN_TYPES)!r}.split()", id="split-string"),
        pytest.param(f"X = {','.join(BUILTIN_TYPES)!r}.split(',')", id="comma-split"),
        pytest.param("X = [" + ", ".join(repr(t) for t in BUILTIN_TYPES[:-1]) + "]", id="nine"),
        pytest.param(
            "X = [" + ", ".join(repr((t, "when to use it")) for t in BUILTIN_TYPES) + "]",
            id="pairs-with-descriptions",
        ),
        pytest.param(
            "def f():\n    return (\n        "
            + ",\n        ".join(map(repr, BUILTIN_TYPES))
            + ",\n    )\n",
            id="inside-a-function-across-lines",
        ),
    ],
)
def test_the_scan_sees_a_second_list_however_it_is_spelled(planted):
    assert second_list_lines(planted), planted


@pytest.mark.parametrize(
    "innocent",
    [
        "X = ['ui_page', 'ui_component', 'api_endpoint']",
        "X = 'ui_page ui_component api_endpoint authentication saas_feature'",
        '"""ui_page ui_component api_endpoint authentication saas_feature data_pipeline"""',
        "X = {'a': 1}",
    ],
)
def test_the_scan_leaves_a_few_names_and_prose_alone(innocent):
    assert second_list_lines(innocent) == []


def test_a_list_planted_in_the_generator_is_caught():
    """integrations/compiler/agents_md.py used to be exempt wholesale, so a second list planted
    anywhere in it passed. It is scanned like every other file: clean as it stands, and the
    same file with a copy added beside the table generator fails."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    source = (repo / "integrations/compiler/agents_md.py").read_text(encoding="utf-8")
    assert second_list_lines(source) == []
    assert second_list_lines(source + f"\n_SNEAKY = [{_SINGLE}]\n")
    assert second_list_lines(source + "\n_SNEAKY = " + repr(" ".join(BUILTIN_TYPES)) + ".split()\n")


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
    assert tuple(type_action.choices) == work_order_type_names()
    assert type_action.default in work_order_type_names()


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
    assert listed == set(BUILTIN_TYPES)


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
    assert seeded == set(BUILTIN_TYPES), (
        "the tuple and the seeded type rows disagree; a type with no row cannot be started, "
        f"a row with no type is unreachable. only-seeded={sorted(seeded - set(BUILTIN_TYPES))} "
        f"only-declared={sorted(set(BUILTIN_TYPES) - seeded)}"
    )
