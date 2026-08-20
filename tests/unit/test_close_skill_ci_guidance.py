"""WO 55d02acf: the close skill must tell the agent about the CI advisory.

The engine emitted `main_ci_warning` and the close mode's SKILL.md never mentioned
it — an engine key with no reader. Close printed the advisory into a result dict
that nothing instructed the agent to surface, so the operator-visible half of
WO-MAINRED-VISIBILITY did not exist.

A docs deliverable is still pinnable. The close gate offered `attest` for a WO
"whose deliverable is operator-local and has no code to check", but this one has
something checkable: the guidance either names the key and the rule, or it does
not. Attesting would have recorded a human promise where a test was available,
which is the substitution this milestone exists to stop.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_CANONICAL = _REPO / "canonical" / "skills" / "ds-workorder" / "modes" / "close" / "SKILL.md"
_PROJECTED = _REPO / "dist" / "plugin" / "skills" / "ds-workorder" / "modes" / "close" / "SKILL.md"


@pytest.fixture(scope="module")
def close_skill() -> str:
    assert _CANONICAL.is_file(), f"close mode SKILL.md missing at {_CANONICAL}"
    return _CANONICAL.read_text(encoding="utf-8")


def test_the_surface_contract_lists_the_ci_keys(close_skill: str) -> None:
    """An agent reading the contract has to know the keys exist, or it cannot
    surface them."""
    assert "main_ci_warning" in close_skill
    assert "main_ci" in close_skill


def test_the_agent_is_told_to_print_the_advisory_verbatim(close_skill: str) -> None:
    """Listing a key is not the same as instructing the agent to use it — the
    original gap was a key present in the engine and absent from the guidance."""
    lowered = close_skill.lower()
    assert "verbatim" in lowered
    assert "advisory" in lowered


def test_the_advisory_is_documented_as_non_blocking(close_skill: str) -> None:
    """A red main from someone else's merge must not stop unrelated work. If the
    guidance omits that, an agent will reasonably treat a red main as a close
    failure — the opposite of the intent (the defect was invisibility, not
    permissiveness)."""
    assert "never blocks" in close_skill or "does not block" in close_skill.lower()


def test_the_pr_smoke_versus_full_ci_rule_is_stated(close_skill: str) -> None:
    """The rule that motivated the whole WO: merge authorization and main's health
    are different claims, measured by different suites."""
    assert "pr-smoke" in close_skill
    assert "full" in close_skill.lower() and "ci" in close_skill.lower()
    assert "merge authorization" in close_skill.lower()
    assert (
        "gh run list --branch main" in close_skill
    ), "the guidance must name the command, not just the concept"


def test_the_projection_matches_canonical(close_skill: str) -> None:
    """dist/plugin ships to plugin installs. Guidance that exists only in
    canonical/ is guidance a plugin user never sees — the same
    two-copies-one-stale shape as the pre-push manifest drift."""
    assert _PROJECTED.is_file(), f"projected close SKILL.md missing at {_PROJECTED}"
    projected = _PROJECTED.read_text(encoding="utf-8")
    assert projected.replace("\r\n", "\n") == close_skill.replace("\r\n", "\n"), (
        "dist/plugin close SKILL.md is stale — rebuild it "
        "(integrations.marketplace.plugin_dist.build_plugin_dist)"
    )


def test_the_mode_file_stays_within_its_line_budget(close_skill: str) -> None:
    """Mode SKILL.md budget is <150 lines (.github/SKILL_STANDARDS.md). Guidance
    nobody reads because the file sprawled is guidance that does not work."""
    lines = close_skill.splitlines()
    assert len(lines) < 150, f"close mode SKILL.md is {len(lines)} lines (budget <150)"
