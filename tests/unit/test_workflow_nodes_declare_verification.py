"""A workflow node says how its effect is verified, or says it is not.

WO 3e0d36a2. Operator on the orchestrator, 2026-09-08: it "doesn't do fucking shit."
Measured, and accurate. ZERO of ~150 nodes across 18 canonical workflows declared a
``completion_check`` -- 0/14 in execute-work-orders.yaml, 0/15 in idea-to-pr.yaml, 0/12 in
feature-research.yaml, every file the same.

The machinery was built (WO 1db6de49) so a node's effect could be observed independently of
what an agent claims, and ``runner.py::_completion_verdict`` is correct, template-resolving
and bounded. Nothing used it: a mechanism with no caller at the MANIFEST level, one layer
above where the reachability gate looks, since that reads Python definitions and not YAML
fields.

A ``command:`` node's text is a PROMPT -- the runner's own comment says
"(LLM instruction prompt)". It is written to a context file, handed to ds-core:build, and
the runner advances. With no completion_check the node lands ``unverified``, which is
honest and useless: the live run orch-verify-1788306820 sat at 1/14 for days, three nodes
"executed" in 0.01-0.03s.

The checker is driven with CONSTRUCTED manifests -- absent, empty, malformed, a reason that
is a shrug -- rather than by editing a real workflow. Mutating a real input tests the
input; it does not test the checker.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.gates.workflow_node_verification import (
    _MIN_REASON_CHARS,
    _node_blocks,
    offenders_in_text,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
NL = chr(10)

_GOOD_REASON = "needs the active work-order id to name its subject (WO e4e85949)"


def _manifest(*node_lines: str) -> str:
    return "name: t" + NL + "nodes:" + NL + NL.join(node_lines) + NL


def test_every_changed_workflow_node_declares_how_it_is_verified():
    """The symptom check for WO 3e0d36a2, against the real changed manifests.

    Failed while every node in every workflow declared nothing at all.
    """
    result = run()
    assert result["status"] == "pass", result["offenders"]


def test_a_node_declaring_nothing_is_refused():
    text = _manifest("  - id: alpha", "    skill: build")
    offenders = offenders_in_text(text)
    assert len(offenders) == 1
    assert offenders[0]["node"] == "alpha"
    assert "neither a completion_check nor" in offenders[0]["message"]


def test_a_node_with_a_completion_check_passes():
    text = _manifest("  - id: alpha", "    completion_check: py -m core.gates.migration_risk")
    assert offenders_in_text(text) == []


def test_a_node_declared_unverifiable_with_a_reason_passes():
    """Not every node CAN be checked. A stated position is what the gate demands."""
    text = _manifest(
        "  - id: alpha", f"    # UNVERIFIED BY DESIGN: {_GOOD_REASON}", "    skill: build"
    )
    assert offenders_in_text(text) == []


def test_a_shrug_is_not_a_reason():
    text = _manifest("  - id: alpha", "    # UNVERIFIED BY DESIGN: later", "    skill: build")
    offenders = offenders_in_text(text)
    assert len(offenders) == 1
    assert "no usable reason" in offenders[0]["message"]
    assert str(_MIN_REASON_CHARS) in offenders[0]["message"]


def test_an_empty_completion_check_does_not_count():
    """`completion_check:` with no value is the field present and saying nothing, which is
    the shape a schema-only check would have accepted."""
    text = _manifest("  - id: alpha", "    completion_check:", "    skill: build")
    offenders = offenders_in_text(text)
    assert len(offenders) == 1, "an empty check was accepted as a declaration"


def test_each_node_is_judged_separately():
    text = _manifest(
        "  - id: alpha",
        "    completion_check: py -m core.gates.migration_risk",
        "  - id: beta",
        "    skill: build",
        "  - id: gamma",
        f"    # UNVERIFIED BY DESIGN: {_GOOD_REASON}",
    )
    offenders = offenders_in_text(text)
    assert [o["node"] for o in offenders] == [
        "beta"
    ], "a neighbour's declaration must not cover an undeclared node"


def test_a_declaration_does_not_leak_past_the_node_list():
    """A top-level key ends the node list, so a trailing document cannot be absorbed into
    the last node's block and silently satisfy it."""
    text = (
        _manifest("  - id: alpha", "    skill: build")
        + "notes: UNVERIFIED BY DESIGN: this is not inside any node at all"
        + NL
    )
    offenders = offenders_in_text(text)
    assert len(offenders) == 1, "a declaration outside the node list satisfied a node"


def test_a_manifest_with_no_nodes_is_not_a_finding():
    assert offenders_in_text("name: t" + NL) == []
    assert offenders_in_text("") == []


def test_node_blocks_reads_the_comment_a_parser_would_discard():
    """The declaration may be a COMMENT, so the checker reads text rather than parsed YAML.

    Pinned because a refactor to yaml.safe_load would silently stop seeing every
    UNVERIFIED BY DESIGN marker -- and then demand something it could not observe.
    """
    text = _manifest("  - id: alpha", f"    # UNVERIFIED BY DESIGN: {_GOOD_REASON}")
    blocks = dict(_node_blocks(text))
    assert "UNVERIFIED BY DESIGN" in blocks["alpha"]
    parsed = yaml.safe_load(text)["nodes"][0]
    assert "UNVERIFIED BY DESIGN" not in str(parsed), (
        "the parser kept the comment, so this test no longer proves the text-reading" " requirement"
    )


def test_the_orchestrator_declares_every_node():
    """The manifest this work order exists for, asserted directly.

    Three nodes carry a real check and eleven state why they cannot; before this the count
    was zero and fourteen.
    """
    text = (REPO_ROOT / "canonical" / "workflows" / "execute-work-orders.yaml").read_text(
        encoding="utf-8"
    )
    assert offenders_in_text(text, "execute-work-orders.yaml") == []

    parsed = yaml.safe_load(text)
    checked = [n["id"] for n in parsed["nodes"] if str(n.get("completion_check") or "").strip()]
    assert len(checked) >= 9, (
        f"only {len(checked)} node(s) carry a real check; the declared-unverifiable escape"
        " is meant to SHRINK, not to absorb every node. It went 0 -> 3 -> 9 as"
        " {{workflow.work_order_id}} made a check able to name its subject; a drop means"
        " nodes were re-declared unverifiable instead of fixed."
    )
    assert "run-gates" in checked, (
        "run-gates is the one node whose effect the runner can verify deterministically"
        " without an LLM -- if it loses its check, nothing in the orchestrator is checked"
    )


@pytest.mark.parametrize("indent", ["  ", "    ", "      "])
def test_the_node_id_pattern_tolerates_indentation(indent):
    """Manifests in this repo indent list items differently; a pattern pinned to one depth
    would silently see no nodes and report every file clean."""
    text = "nodes:" + NL + f"{indent}- id: alpha" + NL + f"{indent}  skill: build" + NL
    assert len(offenders_in_text(text)) == 1


# --------------------------------------------------------------------------------------
# A GATE MANIFEST IS NOT A NODE WORKFLOW. canonical/workflows/pre-push.yaml declares
# `gates:`, and its entries also begin with `- id:` -- so scanning the whole file made this
# gate demand a completion_check on every PRE-PUSH GATE, including itself. Those entries
# carry real executable `command:` lists and are run by a different engine.
#
# Caught on a push, not locally: the gate was validated BEFORE pre-push.yaml was edited to
# register it, so the run that would have failed never happened. Scope-to-diff bounds where
# to hunt; this is the other half -- what the change invalidated.
# --------------------------------------------------------------------------------------


def test_a_manifest_without_a_nodes_key_is_skipped():
    gate_manifest = (
        "name: pre-push" + NL + "gates:" + NL + "  - id: pin-tests" + NL + "    tier: blocking" + NL
    )
    assert offenders_in_text(gate_manifest, "pre-push.yaml") == []


def test_the_real_gate_manifest_is_skipped():
    """Pinned against the actual file, because the synthetic case above would pass even if
    the real manifest's shape differed from my reduction of it."""
    text = (REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml").read_text(encoding="utf-8")
    assert "gates:" in text, "pre-push.yaml no longer declares gates; this lock is stale"
    assert offenders_in_text(text, "pre-push.yaml") == []


def test_only_the_nodes_section_is_scanned():
    """A `- id:` entry under another top-level key must not be read as a node."""
    text = (
        "name: t"
        + NL
        + "nodes:"
        + NL
        + "  - id: alpha"
        + NL
        + "    completion_check: py -m core.gates.migration_risk"
        + NL
        + "gates:"
        + NL
        + "  - id: some-gate"
        + NL
        + "    tier: blocking"
        + NL
    )
    assert offenders_in_text(text) == [], "an entry outside the nodes section was judged as a node"


def test_a_workflow_with_nodes_is_still_scanned_when_it_also_has_other_keys():
    """The converse: skipping must key on the ABSENCE of nodes, not on the presence of
    another section, or one extra key would switch the gate off for a real workflow."""
    text = (
        "name: t"
        + NL
        + "gates:"
        + NL
        + "  - id: some-gate"
        + NL
        + "nodes:"
        + NL
        + "  - id: alpha"
        + NL
        + "    skill: build"
        + NL
    )
    offenders = offenders_in_text(text)
    assert [o["node"] for o in offenders] == ["alpha"]


# --------------------------------------------------------------------------------------
# A CHECK MUST BE ABLE TO NAME ITS SUBJECT. Eight orchestrator nodes were declared
# unverifiable because `<active_work_order_id>` was a prose placeholder nothing
# substituted -- and it could not be inferred: 22 work orders were `in_progress` in the
# authority at once, so "the active work order" is ambiguous. Inferring by recency is the
# option NOT taken; that is the attribution guess the stop hook was corrected for, which
# stamped every edit in a project with whichever work order started last.
# --------------------------------------------------------------------------------------


def test_a_bound_work_order_resolves_in_a_check():
    from control.execution.workflow.engine import resolve_templates

    wf = {"params": {"work_order_id": "wo-1234"}, "nodes": {}}
    resolved = resolve_templates("ds work-order tasks {{workflow.work_order_id}}", wf)
    assert resolved == "ds work-order tasks wo-1234"


def test_an_unbound_work_order_leaves_the_literal_in_place():
    """NOT an empty string. Substituting nothing would silently turn a work-order-scoped
    query into a repo-global one; leaving the template makes the check fail and the node
    block with the reason, which is what the resolver's own docstring prescribes."""
    from control.execution.workflow.engine import resolve_templates

    for wf in ({"params": {"work_order_id": ""}, "nodes": {}}, {"nodes": {}}):
        resolved = resolve_templates("ds work-order tasks {{workflow.work_order_id}}", wf)
        assert resolved == "ds work-order tasks {{workflow.work_order_id}}"


def test_start_accepts_the_binding():
    """The CLI must expose it, or the parameter can never be set.

    Driven through the REAL registrar rather than asserting on source text: a source match
    would pass against a flag registered on the wrong subcommand.
    """
    import argparse

    from interfaces.cli.ds_workflow import add_workflow_subcommand

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    add_workflow_subcommand(sub)

    workflow = sub.choices.get("workflow")
    assert workflow is not None, "the workflow command group disappeared"
    start_parser = None
    for action in workflow._subparsers._group_actions:  # noqa: SLF001
        start_parser = action.choices.get("start")
        if start_parser is not None:
            break
    assert start_parser is not None, "the start subcommand disappeared"
    assert any(
        "--work-order" in (a.option_strings or []) for a in start_parser._actions  # noqa: SLF001
    ), "workflow start exposes no --work-order, so nothing can bind the run"


def test_the_orchestrators_scoped_checks_name_the_work_order():
    """Every check that queries the authority must be work-order-scoped.

    A repo-global authority query would pass for ANY work order, which is the
    compared-nothing-reported-clean shape wearing a completion check.
    """
    import yaml as _yaml

    text = (REPO_ROOT / "canonical" / "workflows" / "execute-work-orders.yaml").read_text(
        encoding="utf-8"
    )
    for node in _yaml.safe_load(text)["nodes"]:
        check = str(node.get("completion_check") or "")
        if "work-order" in check and "artifact" not in check:
            assert "{{workflow.work_order_id}}" in check, (
                f"node {node['id']!r} queries work orders without naming one:"
                f" {check!r} would pass for any work order in the authority"
            )
