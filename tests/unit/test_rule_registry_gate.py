"""The rule-registry gate must refuse an unclassified rule and an unrunnable check.

A gate that cannot fail is the defect this whole registry exists to remove, so each case
here feeds the real gate an input it must reject. The registry is redirected at a temporary
file rather than asserted against the live one: a test that only passes while the shipped
registry happens to be clean proves nothing about the gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.gates import rule_registry


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """Point the gate at a scratch registry this test controls."""
    path = tmp_path / "rules.yml"
    monkeypatch.setattr(rule_registry, "REGISTRY", path)
    return path


def _write(path: Path, body: str) -> None:
    path.write_text("version: 1\nrules:\n" + body, encoding="utf-8")


def test_a_classified_and_runnable_rule_passes(registry) -> None:
    """The baseline. Without it the refusals below prove only that the gate says no."""
    _write(
        registry,
        "  - id: real\n"
        "    statement: A real rule.\n"
        "    enforced_by:\n"
        "      - tests/unit/test_rule_registry_gate.py::test_a_classified_and_runnable_rule_passes\n",
    )
    result = rule_registry.run()
    assert result["status"] == "pass", result["errors"]
    assert result["enforced"] == 1


def test_an_unclassified_rule_is_refused(registry) -> None:
    """Neither enforced nor declared guidance: the status quo the registry exists to end."""
    _write(registry, "  - id: unclassified\n    statement: Something everyone must do.\n")
    result = rule_registry.run()
    assert result["status"] == "fail"
    assert any("neither enforced_by nor guidance" in e for e in result["errors"]), result["errors"]


def test_guidance_without_a_reason_is_refused(registry) -> None:
    """'No check is possible' is a claim, and an unexplained one hides an unenforced rule."""
    _write(registry, "  - id: bare\n    statement: Use judgment.\n    guidance: true\n")
    result = rule_registry.run()
    assert result["status"] == "fail"
    assert any("no `why`" in e for e in result["errors"]), result["errors"]


def test_a_check_that_does_not_exist_is_refused(registry) -> None:
    """An enforced_by naming a missing file is no check at all."""
    _write(
        registry,
        "  - id: ghost\n"
        "    statement: A rule pointing at nothing.\n"
        "    enforced_by:\n"
        "      - tests/unit/test_this_file_does_not_exist.py::test_nope\n",
    )
    result = rule_registry.run()
    assert result["status"] == "fail"
    assert any("missing file" in e for e in result["errors"]), result["errors"]


def test_a_check_that_collects_nothing_is_refused(registry) -> None:
    """The rot found on eight acceptance criteria this session.

    pytest exits 5 for no-tests-collected and 4 for a usage error, and neither is a test
    failure -- so a gate reading zero-versus-nonzero cannot tell "the rule is broken" from
    "the check stopped addressing anything". This file exists, the named test does not.
    """
    _write(
        registry,
        "  - id: renamed\n"
        "    statement: A rule whose test was renamed.\n"
        "    enforced_by:\n"
        "      - tests/unit/test_rule_registry_gate.py::test_a_name_that_was_renamed_away\n",
    )
    result = rule_registry.run()
    assert result["status"] == "fail"
    assert any("not runnable" in e for e in result["errors"]), result["errors"]


def test_claiming_both_enforced_and_guidance_is_refused(registry) -> None:
    """Declaring both hides which one the gate trusts."""
    _write(
        registry,
        "  - id: both\n"
        "    statement: Ambiguous.\n"
        "    guidance: true\n"
        "    why: because\n"
        "    enforced_by:\n"
        "      - tests/unit/test_rule_registry_gate.py::test_claiming_both_enforced_and_guidance_is_refused\n",
    )
    result = rule_registry.run()
    assert result["status"] == "fail"
    assert any("both enforced_by and guidance" in e for e in result["errors"]), result["errors"]


def test_a_missing_registry_fails_rather_than_passing_vacuously(registry) -> None:
    """No registry must not read as no violations.

    The compared-nothing-reported-clean shape: a gate that passes because it found nothing
    to examine is worse than no gate, because it reports confidence it has not earned.
    """
    assert not registry.exists()
    result = rule_registry.run()
    assert result["status"] == "fail"
    assert any("missing" in e for e in result["errors"]), result["errors"]


def test_the_shipped_registry_passes() -> None:
    """The live canonical/rules.yml must itself satisfy the gate.

    Separate from the cases above, which drive scratch registries. If this fails, a rule
    was added without being classified or its check has rotted.
    """
    result = rule_registry.run()
    assert result["status"] == "pass", result["errors"]
    assert result["rule_count"] > 0


# --------------------------------------------------------------------------------------
# PARTIAL ENFORCEMENT. The contract was enforced XOR guidance, which could not describe a
# rule a check covers only partly -- so two rules sat as pure `guidance` while real checks
# already covered part of each. Filing them that way understated the substrate and made the
# registry read as more helpless than it is.
# --------------------------------------------------------------------------------------

_LONG_RESIDUAL = (
    "The gate proves a claim cites something checkable but cannot prove the cited thing "
    "was run, so a fabricated figure beside a real citation still passes."
)


def test_enforced_plus_residual_risk_is_accepted_and_counted(registry) -> None:
    _write(
        registry,
        "  - id: partial\n"
        "    statement: A rule a check covers only partly.\n"
        "    enforced_by:\n"
        "      - tests/unit/test_rule_registry_gate.py::test_a_classified_and_runnable_rule_passes\n"
        f"    residual_risk: >\n      {_LONG_RESIDUAL}\n",
    )
    result = rule_registry.run()
    assert result["status"] == "pass", result["errors"]
    assert result["enforced"] == 1
    assert result["partially_enforced"] == 1, "partial coverage must be counted, not hidden"


def test_residual_risk_without_a_check_is_refused(registry) -> None:
    """With no check there is no residual -- only the whole rule unenforced.

    Otherwise `residual_risk` becomes a way to describe a gap while looking like coverage,
    which is the label-instead-of-a-check problem in a new costume.
    """
    _write(
        registry,
        "  - id: residual_only\n"
        "    statement: A rule with a residual and no check.\n"
        f"    residual_risk: >\n      {_LONG_RESIDUAL}\n",
    )
    result = rule_registry.run()
    assert result["status"] == "fail"
    assert any("residual_risk with no enforced_by" in e for e in result["errors"])


def test_a_perfunctory_residual_is_refused(registry) -> None:
    """ "Some cases" is not a residual. The uncovered part has to be nameable, or nobody can
    later close it and the field becomes decoration."""
    _write(
        registry,
        "  - id: thin\n"
        "    statement: A rule with a shrug for a residual.\n"
        "    enforced_by:\n"
        "      - tests/unit/test_rule_registry_gate.py::test_a_classified_and_runnable_rule_passes\n"
        "    residual_risk: some cases\n",
    )
    result = rule_registry.run()
    assert result["status"] == "fail"
    assert any("states too little" in e for e in result["errors"])


def test_a_fully_enforced_rule_needs_no_residual(registry) -> None:
    """The common case must stay simple: nothing is required beyond enforced_by."""
    _write(
        registry,
        "  - id: full\n"
        "    statement: A fully covered rule.\n"
        "    enforced_by:\n"
        "      - tests/unit/test_rule_registry_gate.py::test_a_classified_and_runnable_rule_passes\n",
    )
    result = rule_registry.run()
    assert result["status"] == "pass", result["errors"]
    assert result["partially_enforced"] == 0


def test_the_both_error_points_at_the_partial_state(registry) -> None:
    """A rule declaring enforced AND guidance is usually reaching for partial coverage, so
    the refusal names the state that actually fits rather than just saying no."""
    _write(
        registry,
        "  - id: both\n"
        "    statement: A rule claiming both.\n"
        "    guidance: true\n"
        "    why: because\n"
        "    enforced_by:\n"
        "      - tests/unit/test_rule_registry_gate.py::test_a_classified_and_runnable_rule_passes\n",
    )
    result = rule_registry.run()
    assert result["status"] == "fail"
    assert any("residual_risk" in e for e in result["errors"])


def test_the_shipped_registry_has_no_unenforced_rule() -> None:
    """Every rule is enforced, and the two partial ones name what they do not cover.

    This is a snapshot of an achieved state, NOT a ban on future guidance: a rule that
    genuinely admits no check should still be filed as guidance with a why, and punishing
    that honesty would push the next unenforceable rule back into prose. What the assertion
    protects is that nothing sits unclassified, and that a rule is not filed as guidance
    while a check already covers part of it -- which is what had happened twice.
    """
    result = rule_registry.run()
    assert result["status"] == "pass", result["errors"]
    assert result["guidance"] == 0, (
        "a rule is filed as guidance; check whether a real check already covers part of it,"
        " in which case it belongs under enforced_by + residual_risk"
    )
    assert result["enforced"] == result["rule_count"]
    assert result["partially_enforced"] >= 2
