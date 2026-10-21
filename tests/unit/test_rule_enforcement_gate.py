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
# A node id is resolved to the test, not just to the file
# --------------------------------------------------------------------------
#
# `file::name` used to count as resolved when `file` existed. A test renamed or deleted
# underneath a rule left the rule claiming enforcement by something that was no longer
# there, and the gate printed OK (#896; found on `a-work-order-type-is-refused-at-the-door`
# and on `detector-lane-declares-what-it-leaves-undecided`, the latter dangling for weeks).

_SAMPLE = """\
import pytest


def test_plain():
    pass


async def test_async():
    pass


@pytest.mark.parametrize("value", [1, 2])
@pytest.mark.slow
def test_decorated(value):
    pass


class TestOuter:
    def test_method(self):
        pass

    class TestInner:
        def test_deep(self):
            pass


def test_duplicated():
    pass


def test_duplicated():
    pass


test_a_variable = 3
test_an_alias = test_plain


def test_wraps_a_function():
    def test_nested_in_a_function():
        pass


if True:
    def test_guarded():
        pass
"""


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """A throwaway tree the gate resolves against, so each case controls the file."""
    from core.gates import rule_enforcement

    monkeypatch.setattr(rule_enforcement, "REPO_ROOT", tmp_path)
    (tmp_path / "t.py").write_text(_SAMPLE, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "node",
    [
        "t.py::test_plain",
        "t.py::test_async",
        "t.py::test_decorated",
        "t.py::TestOuter",
        "t.py::TestOuter::test_method",
        "t.py::TestOuter::TestInner",
        "t.py::TestOuter::TestInner::test_deep",
        "t.py::test_duplicated",
        "t.py::test_guarded",
        # a parametrised id resolves when the function does; the ids are generated at
        # collection time and may hold `::` and `]` themselves
        "t.py::test_decorated[1]",
        "t.py::test_decorated[a-b]",
        "t.py::test_decorated[x::y]",
        "t.py::TestOuter::test_method[1]",
    ],
)
def test_a_node_that_exists_resolves(fake_repo, node):
    assert _resolve(node) is None


@pytest.mark.parametrize(
    "node,fragment",
    [
        # the case the gate exists for: the test was renamed or deleted
        ("t.py::test_renamed_away", "`test_renamed_away` defined in t.py"),
        ("t.py::test_plain_renamed[1]", "`test_plain_renamed` defined in t.py"),
        # right name, wrong class
        ("t.py::TestInner::test_deep", "`TestInner` defined in t.py"),
        ("t.py::TestOuter::test_deep", "`test_deep` defined in TestOuter"),
        (
            "t.py::TestOuter::TestInner::test_method",
            "`test_method` defined in TestOuter::TestInner",
        ),
        # a function has no tests inside it, and an assignment is not a test
        ("t.py::test_wraps_a_function::test_nested_in_a_function", "is a function, not a class"),
        ("t.py::test_a_variable", "`test_a_variable` defined in t.py"),
        ("t.py::test_an_alias", "`test_an_alias` defined in t.py"),
        ("t.py::test_plain::", "empty segment"),
        ("t.py::", "empty segment"),
        ("t.py::::test_plain", "empty segment"),
    ],
)
def test_a_node_that_does_not_exist_is_refused_and_named(fake_repo, node, fragment):
    why = _resolve(node)
    assert why is not None, f"{node} resolved but should not"
    assert fragment in why


def test_a_missing_file_still_says_no_such_test_file(fake_repo):
    assert _resolve("gone.py::test_plain") == "no such test file"


def test_a_node_into_a_non_python_file_is_refused(fake_repo):
    (fake_repo / "notes.md").write_text("def test_plain(): pass\n", encoding="utf-8")
    assert _resolve("notes.md::test_plain") == "node id into a non-python file"


def test_a_test_file_that_does_not_parse_fails_with_a_message_not_a_crash(fake_repo):
    (fake_repo / "broken.py").write_text("def test_a(:\n    pass\n", encoding="utf-8")
    why = _resolve("broken.py::test_a")
    assert why is not None and "does not parse" in why and "line 1" in why


def test_a_test_file_that_is_not_utf8_fails_with_a_message_not_a_crash(fake_repo):
    (fake_repo / "latin.py").write_bytes(b"def test_a():\n    x = '\xe9'\n")
    why = _resolve("latin.py::test_a")
    assert why is not None and "not readable" in why


def test_resolving_a_node_never_imports_or_runs_the_test_module(fake_repo):
    """Reading source is the whole method. A test module may need a database, a network,
    or a fixture the gate has no business setting up, and importing it would execute
    whatever sits at module level on every push."""
    marker = fake_repo / "ran.txt"
    (fake_repo / "side_effect.py").write_text(
        f"open({str(marker)!r}, 'w').write('ran')\n"
        "raise RuntimeError('imported')\n"
        "def test_x():\n    pass\n",
        encoding="utf-8",
    )
    assert _resolve("side_effect.py::test_x") is None
    assert not marker.exists()


def test_a_file_is_parsed_once_however_many_rules_name_it(fake_repo, monkeypatch):
    """The gate runs on every push; 171 references over a few dozen files must cost a few
    dozen parses."""
    import ast

    from core.gates import rule_enforcement

    calls = []
    real = ast.parse
    monkeypatch.setattr(
        rule_enforcement.ast, "parse", lambda *a, **k: calls.append(1) or real(*a, **k)
    )
    path = _registry(
        fake_repo,
        """\
        rules:
          - id: a-rule
            statement: Something ought to be true.
            source: nowhere.py
            enforced_by:
              - t.py::test_plain
              - t.py::test_async
              - t.py::TestOuter::test_method
        """,
    )
    assert audit(path)["broken"] == []
    assert len(calls) == 1


def test_a_dangling_node_fails_the_audit_with_the_rule_the_reference_and_the_gap(fake_repo):
    path = _registry(
        fake_repo,
        """\
        rules:
          - id: a-rule-whose-test-was-renamed
            statement: Something ought to be true.
            source: nowhere.py
            enforced_by:
              - t.py::test_plain
              - t.py::test_plain_but_renamed
        """,
    )
    report = audit(path)
    assert report["references_checked"] == 2
    assert [(b["rule"], b["reference"]) for b in report["broken"]] == [
        ("a-rule-whose-test-was-renamed", "t.py::test_plain_but_renamed")
    ]
    assert "`test_plain_but_renamed` defined in t.py" in report["broken"][0]["why"]


def test_the_command_exits_nonzero_and_names_a_dangling_node(fake_repo, monkeypatch, capsys):
    from core.gates import rule_enforcement

    path = _registry(
        fake_repo,
        """\
        rules:
          - id: a-rule-whose-test-was-renamed
            statement: Something ought to be true.
            source: nowhere.py
            enforced_by:
              - t.py::test_plain_but_renamed
        """,
    )
    monkeypatch.setattr(rule_enforcement, "REGISTRY", path)
    assert rule_enforcement.main() == 1
    out = capsys.readouterr().out
    assert "a-rule-whose-test-was-renamed" in out
    assert "t.py::test_plain_but_renamed" in out
    assert "`test_plain_but_renamed` defined in t.py" in out


def test_the_known_dangling_reference_fails_the_real_register_when_it_comes_back(tmp_path):
    """The register as shipped passes; the same register with a node that does not exist
    added to the rule that dangled for weeks is refused, naming that rule. Kept as a test
    so the real register, not only a fixture, is shown to be reachable by the check."""
    shipped = (REPO_ROOT / "canonical" / "rules.yml").read_text(encoding="utf-8")
    assert audit()["broken"] == []

    anchor = "      - core/gates/review_lane_registry.py\n"
    mutated = shipped.replace(
        anchor,
        anchor
        + "      - tests/unit/test_round_table.py::test_no_lane_asks_more_than_its_enforcement_x\n",
        1,
    )
    assert mutated != shipped, "the mutation did not apply; the rule moved"
    path = tmp_path / "rules.yml"
    path.write_text(mutated, encoding="utf-8")
    broken = audit(path)["broken"]
    assert [b["rule"] for b in broken] == ["detector-lane-declares-what-it-leaves-undecided"]
    assert broken[0]["reference"].endswith("test_no_lane_asks_more_than_its_enforcement_x")


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
        # the review loop: the substrate makes it expressible, the reading is not
        # something a check can do
        "work-found-wanting-is-the-same-work-orders-unfinished-work",
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
