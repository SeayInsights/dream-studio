"""A rule that claims enforcement must name an enforcer that exists.

`canonical/rules.yml` is the register that separates the statements something enforces
from the ones nothing does — its header says the substrate was "a lot of prose laid on
top of each other as suggestions with no rules, evals, or really any real test that doing
anything they are supposed to". Every rule names the modules and pytest nodes holding it
up.

`core/gates/rule_registry.py` checked those names. It was culled in `67ba10e`, in the same
sweep that removed several of the enforcers it would have been checking — so the register
kept asserting enforcement for gates that no longer existed, and the one thing that could
have noticed went with them.

MEASURED WHEN THIS WAS WRITTEN: 21 of 102 `enforced_by` references across 7 of 34 rules
named a module or test file that is not in the tree.

THE DECLARATION IS THE OTHER HALF, and it is why this is not just a path checker. Five of
those seven lost enforcement because the gate was deliberately removed. Deleting the rules
would lose the statements; leaving them claiming enforcement would keep lying. So a rule
may declare `unenforced:` with a reason — and the gate PRINTS that pile on every run, pass
or fail, because a register whose whole purpose is to make the unenforced visible fails at
its job if the declaration only shows up in an error.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from core.gates.rule_enforcement import MIN_REASON, _resolve, audit

REPO_ROOT = Path(__file__).resolve().parents[2]


def _registry(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "rules.yml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# The repository's own register holds
# --------------------------------------------------------------------------


def test_every_enforcement_claim_in_the_register_resolves():
    """The gate's own subject. A failure here means a rule says something holds it up
    that is not in the tree — which is the state the register exists to prevent."""
    report = audit()
    assert report["broken"] == [], "\n".join(
        f"  {b['rule']}: {b['why']} -> {b['reference']}" for b in report["broken"]
    )


def test_the_register_still_has_rules_to_check():
    """A gate that passes because it found nothing to look at is the failure mode this
    whole file exists for, one level up."""
    report = audit()
    assert report["rules"] >= 30
    assert report["references_checked"] >= 50


# --------------------------------------------------------------------------
# What a broken claim looks like
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reference,why",
    [
        ("core.gates.evidence_backed_output", "no such module"),
        ("tests/unit/test_gone.py::test_a_thing", "no such test file"),
        ("core/gates/nowhere.py", "no such path"),
        ("", "empty reference"),
    ],
)
def test_a_reference_that_does_not_resolve_is_named_with_its_reason(reference, why):
    assert _resolve(reference) == why


@pytest.mark.parametrize(
    "reference",
    [
        "core.gates.unverified_claims",
        "tests/unit/test_rule_enforcement_gate.py::test_the_register_still_has_rules_to_check",
        "core/gates/rule_enforcement.py",
        "canonical/rules.yml",
    ],
)
def test_a_reference_that_resolves_passes(reference):
    assert _resolve(reference) is None


def test_a_rule_with_neither_enforcement_nor_a_declaration_is_refused(tmp_path):
    """Silence is the state the register was written to end."""
    path = _registry(
        tmp_path,
        """\
        rules:
          - id: a-rule-that-says-nothing
            statement: Something ought to be true.
            source: nowhere.py
            enforced_by: []
        """,
    )
    broken = audit(path)["broken"]
    assert len(broken) == 1
    assert "no unenforced declaration" in broken[0]["why"]


# --------------------------------------------------------------------------
# The declaration, and that it is not a bypass
# --------------------------------------------------------------------------


def test_a_declared_rule_passes_and_is_counted(tmp_path):
    path = _registry(
        tmp_path,
        """\
        rules:
          - id: a-rule-nothing-holds-up
            statement: Something ought to be true.
            source: nowhere.py
            unenforced: >
              The gate that held this up was removed deliberately and nothing replaced it.
        """,
    )
    report = audit(path)
    assert report["broken"] == []
    assert [d["rule"] for d in report["declared"]] == ["a-rule-nothing-holds-up"]


def test_a_shrug_is_not_a_declaration(tmp_path):
    """Same floor as `admission.py`'s --why, deliberately: one repo, one shape for
    "I cannot enforce this, and here is why". An escape hatch that costs nothing
    becomes the norm."""
    path = _registry(
        tmp_path,
        """\
        rules:
          - id: a-rule-nothing-holds-up
            statement: Something ought to be true.
            source: nowhere.py
            unenforced: gone
        """,
    )
    broken = audit(path)["broken"]
    assert len(broken) == 1
    assert str(MIN_REASON) in broken[0]["why"]


def test_a_rule_cannot_be_both_held_up_and_not(tmp_path):
    """Declaring unenforced while still listing enforcers would let a rule keep its
    claim and its excuse at once, which is the one way this contract could be gamed
    without lying outright."""
    path = _registry(
        tmp_path,
        """\
        rules:
          - id: a-rule-having-it-both-ways
            statement: Something ought to be true.
            source: nowhere.py
            unenforced: >
              The gate that held this up was removed deliberately and nothing replaced it.
            enforced_by:
              - canonical/rules.yml
        """,
    )
    broken = audit(path)["broken"]
    assert len(broken) == 1
    assert "pick one" in broken[0]["why"]


# --------------------------------------------------------------------------
# The five the cull left behind are declared, not quietly dropped
# --------------------------------------------------------------------------


def test_the_rules_the_cull_left_unenforced_say_so_in_writing():
    """3b2dc373 and 67ba10e removed the gates holding these up. The statements are kept
    because the concerns are real; what changed is that the register no longer claims
    something enforces them."""
    declared = {d["rule"] for d in audit()["declared"]}
    assert declared == {
        "the-unclassified-pile-may-only-shrink",
        "a-decided-question-has-one-supported-read",
        "a-gate-does-not-get-slower-as-it-is-adopted",
        "a-workflow-node-states-how-it-is-verified",
        "a-completion-check-names-its-subject",
    }


def test_every_declaration_names_the_commit_that_removed_its_enforcer():
    """A declaration that does not say what went is a shrug with more words. Each of
    these can be followed back to the change that made it true."""
    for item in audit()["declared"]:
        assert any(
            sha in item["reason"] for sha in ("3b2dc373", "67ba10e")
        ), f"{item['rule']} does not name the commit that removed its enforcer"


# --------------------------------------------------------------------------
# Guidance is a classification, not a regression
# --------------------------------------------------------------------------


def test_a_guidance_rule_passes_and_is_counted_apart(tmp_path):
    """The two piles mean different things and are reported separately.

    `unenforced` says an enforcer existed and a named commit removed it, so that list is
    a debt meant to shrink. `guidance` says no static check can settle the statement at
    all. Counting them together made the debt look larger and, worse, unfixable -- there
    is no enforcement to restore for a statement about how the model should behave.
    """
    path = _registry(
        tmp_path,
        """\
        rules:
          - id: a-rule-only-an-eval-can-settle
            statement: The model should surface what the call returned.
            source: nowhere.py
            guidance: true
            why: >
              No static check can tell a recited answer from a read one; this is an eval.
        """,
    )
    report = audit(path)
    assert report["broken"] == []
    assert report["declared"] == [], "guidance must not inflate the unenforced pile"
    assert [g["rule"] for g in report["guidance"]] == ["a-rule-only-an-eval-can-settle"]


def test_guidance_needs_a_why_of_its_own(tmp_path):
    """Same floor as the other escape. A classification that costs nothing to claim is
    the way every hard rule eventually becomes guidance."""
    path = _registry(
        tmp_path,
        """\
        rules:
          - id: a-rule-waving-it-through
            statement: Something ought to be true.
            source: nowhere.py
            guidance: true
            why: hard
        """,
    )
    broken = audit(path)["broken"]
    assert len(broken) == 1
    assert str(MIN_REASON) in broken[0]["why"]


def test_guidance_without_a_why_at_all_is_refused(tmp_path):
    """`guidance: true` alone is the shrug in its purest form."""
    path = _registry(
        tmp_path,
        """\
        rules:
          - id: a-rule-with-a-bare-claim
            statement: Something ought to be true.
            source: nowhere.py
            guidance: true
        """,
    )
    broken = audit(path)["broken"]
    assert len(broken) == 1
    assert str(MIN_REASON) in broken[0]["why"]


def test_a_rule_cannot_be_guidance_and_enforced_at_once(tmp_path):
    """Same objection as the unenforced case: a rule keeping its claim and its excuse."""
    path = _registry(
        tmp_path,
        """\
        rules:
          - id: a-rule-having-it-both-ways
            statement: Something ought to be true.
            source: nowhere.py
            guidance: true
            why: >
              No static check can settle this one, it is an instruction to the model.
            enforced_by:
              - canonical/rules.yml
        """,
    )
    broken = audit(path)["broken"]
    assert len(broken) == 1
    assert "pick one" in broken[0]["why"]


def test_a_rule_cannot_be_guidance_and_a_removed_enforcer_at_once(tmp_path):
    """The two states answer different questions, and a rule that claims both tells us
    neither: either an enforcer was removed, or none could have existed."""
    path = _registry(
        tmp_path,
        """\
        rules:
          - id: a-rule-claiming-both-excuses
            statement: Something ought to be true.
            source: nowhere.py
            guidance: true
            why: >
              No static check can settle this one, it is an instruction to the model.
            unenforced: >
              The gate that held this up was removed deliberately and nothing replaced it.
        """,
    )
    broken = audit(path)["broken"]
    assert len(broken) == 1
    assert "pick one" in broken[0]["why"]


def test_the_registers_guidance_entries_are_the_ones_the_dissolution_produced(tmp_path):
    """Pinned like the unenforced set, for the same reason: the pile is only meaningful
    while every entry is deliberate. Every one came out of a dissolved skill pack, where
    it was a numbered instruction charged as context on every invocation and enforced by
    nothing: three from ds-milestone, eight from ds-project, two from ds-workorder.

    Widening this set is meant to cost an edit. A rule declared guidance is a rule no gate
    will ever hold up, so the list growing quietly is exactly how a repo talks itself out
    of enforcement one statement at a time."""
    assert {g["rule"] for g in audit()["guidance"]} == {
        # ds-milestone
        "surfaced-state-is-what-the-call-returned",
        "a-gate-bypass-needs-an-explicit-yes",
        "a-read-does-not-chain-into-a-mutation",
        # ds-project: the interview, and what it must not write down
        "an-interview-asks-one-question-at-a-time",
        "a-field-with-no-answer-is-asked-for-never-filled-in",
        "a-rejection-is-revised-not-regenerated",
        "an-ambiguous-reference-stops-and-asks",
        "a-destructive-action-needs-an-unambiguous-yes",
        "a-scope-covering-two-projects-is-split-before-it-is-scoped",
        "a-milestone-is-something-that-can-be-demonstrated",
        "only-the-active-milestone-is-decomposed",
        # ds-workorder: the one thing in that pack no check could settle
        "a-context-artifact-leads-with-the-prompt-chain",
        # Recovered from the dissolved execute mode when main went red: it was the
        # one statement there that no other rule covered.
        "a-claim-with-an-exact-answer-is-computed-not-read",
    }


def test_the_gate_is_registered_in_the_pre_push_manifest():
    """The register's previous checker was culled and nothing noticed for weeks. A gate
    that exists in no manifest is the defect it was built to catch."""
    import yaml

    manifest = yaml.safe_load(
        (REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml").read_text(encoding="utf-8")
    )
    gates = manifest["gates"] if isinstance(manifest, dict) else manifest
    entry = next((g for g in gates if g.get("id") == "rule-enforcement"), None)
    assert entry is not None, "rule-enforcement is not registered in pre-push.yaml"
    assert entry["command"] == ["py", "-m", "core.gates.rule_enforcement"]
    assert entry["tier"] == "blocking"
    assert "fail_hint" in entry
