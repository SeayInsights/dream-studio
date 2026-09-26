"""Every skill mode either has a specialist, or says why it has none.

`packs.yaml` declares 86 modes. Nine had an agent. The eleven audit modes sitting beside
`quality/accessibility` — which HAS one — had none, and nothing in the repository recorded
whether that was a decision or an oversight.

**A gap nobody wrote down is indistinguishable from a choice nobody made.** So every mode
now appears in `canonical/agents/coverage.yml` exactly once, on one side of the line or
the other, and this gate refuses a mode that has not been placed.

The gate deliberately does not judge WHICH side a mode belongs on. That is a person's
call, it is recorded in the file with its reasoning, and it is reviewable there. What is
mechanical — is every mode accounted for, does every named agent exist, is every reason
long enough to be one — is what gets enforced.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from core.gates.agent_coverage import (
    MIN_REASON,
    audit,
    declared_modes,
    modes_on_disk,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# The repository is covered, and stays covered
# --------------------------------------------------------------------------


def test_every_mode_is_accounted_for():
    report = audit()
    assert report["problems"] == [], "\n".join(f"  {p}" for p in report["problems"])


def test_the_gate_has_something_to_check():
    """A gate that passes by finding nothing is the defect this whole session kept
    finding. 85 modes were on disk when this was written, 24 of them with a specialist."""
    report = audit()
    assert report["modes"] >= 60, f"only {report['modes']} modes found — has the tree moved?"
    assert report["with_agent"] >= 20, f"only {report['with_agent']} modes have a specialist"
    assert report["declared_without"] >= 40, (
        "almost nothing is declared without an agent, which would mean the rule stopped "
        "refusing anything"
    )


def test_the_declaration_and_the_tree_agree_exactly():
    declared = {str(row["mode"]) for row in declared_modes()}
    assert declared == modes_on_disk()


@pytest.mark.parametrize("row", declared_modes(), ids=lambda r: str(r["mode"]))
def test_a_declared_agent_is_actually_compiled(row):
    """A coverage row naming an agent that does not exist is the dangling-instruction
    shape the instruction-commands gate refuses, one layer up."""
    name = row.get("agent")
    if not name:
        pytest.skip("declared without an agent")
    assert (REPO_ROOT / "canonical" / "agents" / f"{name}.md").is_file()


@pytest.mark.parametrize("row", declared_modes(), ids=lambda r: str(r["mode"]))
def test_a_mode_without_an_agent_says_why_at_length(row):
    if row.get("agent"):
        pytest.skip("has an agent")
    reason = " ".join(str(row.get("no_agent") or "").split())
    assert len(reason) >= MIN_REASON, f"{row['mode']}: {len(reason)} characters is a shrug"


def test_the_audit_fan_out_all_have_specialists():
    """`audit:` is the one trigger in the tree that several modes share, so one operator
    word convenes five specialists at once. Running in parallel is what a dispatch buys,
    and it is the clearest case for an agent anywhere in this repository."""
    declared = {str(r["mode"]): r for r in declared_modes()}
    for mode in (
        "code-health/code-quality",
        "data/database",
        "quality/security",
        "code-health/testing",
        "quality/types-deps",
    ):
        assert mode in declared, f"{mode} is not declared at all"
        assert declared[mode].get("agent"), f"{mode} is in the audit: fan-out and has no agent"
        assert "fan-out" in str(
            declared[mode].get("dispatched_because", "")
        ), f"{mode} has an agent but does not record that a fan-out is why"


def test_the_audit_router_itself_has_no_agent():
    """`code-health/audit` routes `audit:` to the five above. A router has no question of its
    own, and an agent here would be a dispatcher nested inside its own dispatch."""
    declared = {str(r["mode"]): r for r in declared_modes()}
    assert not declared["code-health/audit"].get("agent")
    assert "router" in declared["code-health/audit"]["no_agent"].lower()


def test_a_thin_skill_is_declared_out_with_its_measurement():
    """The negative half of the rule, and the half that keeps it honest. A mode refused
    for being small must say how small, so the decision can be re-checked when the skill
    grows rather than inherited as folklore."""
    declared = {str(r["mode"]): r for r in declared_modes()}
    reason = declared["apps/game-dev"]["no_agent"]
    assert "1092 bytes" in reason, f"the refusal does not carry its measurement: {reason}"
    assert "inline" in reason


# --------------------------------------------------------------------------
# What it refuses
# --------------------------------------------------------------------------


def _coverage(tmp_path: Path, body: str, monkeypatch) -> None:
    import core.gates.agent_coverage as gate

    path = tmp_path / "coverage.yml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    monkeypatch.setattr(gate, "COVERAGE", path)


def test_a_mode_in_neither_state_is_refused(tmp_path, monkeypatch):
    import core.gates.agent_coverage as gate

    _coverage(
        tmp_path,
        """\
        modes:
          - mode: quality/testing
            skill: quality/modes/testing/SKILL.md
        """,
        monkeypatch,
    )
    monkeypatch.setattr(gate, "modes_on_disk", lambda: {"quality/testing"})
    problems = gate.audit()["problems"]
    assert any("neither an agent nor a reason" in p for p in problems), problems


def test_a_mode_on_disk_and_not_declared_is_refused(tmp_path, monkeypatch):
    """The one that matters for the future: a new specialist mode cannot ship with
    nobody able to answer it and nobody having decided that was right."""
    import core.gates.agent_coverage as gate

    _coverage(tmp_path, "modes: []\n", monkeypatch)
    monkeypatch.setattr(gate, "modes_on_disk", lambda: {"quality/a-brand-new-mode"})
    problems = gate.audit()["problems"]
    assert any("not in coverage.yml" in p for p in problems), problems


def test_a_shrug_is_not_a_reason(tmp_path, monkeypatch):
    import core.gates.agent_coverage as gate

    _coverage(
        tmp_path,
        """\
        modes:
          - mode: quality/testing
            skill: quality/modes/testing/SKILL.md
            no_agent: nope
        """,
        monkeypatch,
    )
    monkeypatch.setattr(gate, "modes_on_disk", lambda: {"quality/testing"})
    problems = gate.audit()["problems"]
    assert any(str(MIN_REASON) in p for p in problems), problems


def test_a_mode_cannot_have_it_both_ways(tmp_path, monkeypatch):
    import core.gates.agent_coverage as gate

    _coverage(
        tmp_path,
        """\
        modes:
          - mode: quality/testing
            skill: quality/modes/testing/SKILL.md
            agent: quality-testing
            installed_skill: ds-quality/modes/testing/SKILL.md
            no_agent: it also has a long enough reason for having none
        """,
        monkeypatch,
    )
    monkeypatch.setattr(gate, "modes_on_disk", lambda: {"quality/testing"})
    problems = gate.audit()["problems"]
    assert any("both an agent and a reason" in p for p in problems), problems


def test_the_gate_is_registered_in_the_pre_push_manifest():
    import yaml

    manifest = yaml.safe_load(
        (REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml").read_text(encoding="utf-8")
    )
    gates = manifest["gates"] if isinstance(manifest, dict) else manifest
    entry = next((g for g in gates if g.get("id") == "agent-coverage"), None)
    assert entry is not None, "agent-coverage is not registered in pre-push.yaml"
    assert entry["command"] == ["py", "-m", "core.gates.agent_coverage"]
    assert entry["tier"] == "blocking"
    assert "fail_hint" in entry
