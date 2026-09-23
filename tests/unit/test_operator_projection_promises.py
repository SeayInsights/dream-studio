"""What an install is told exists, exists — and the unenforceable rules reach it.

TWO THINGS THIS FILE HOLDS UP.

`build_agents_md` is the OPERATOR projection: the installer ships it beside the generated
`~/.claude/CLAUDE.md`, whose `@AGENTS.md` import resolves to it. It is what an agent in an
install reads. Until now it told that agent to "invoke `ds-project:resume`" -- a skill
deleted when the project pack was dissolved -- and to call `get_project_state()`,
`mark_task_done(...)` and `close_work_order(...)`, which are internal functions and not
doors anyone is meant to reach for. Three dissolutions landed before anything noticed,
because nothing checked that this file's promises resolve.

And `canonical/rules.yml` is not shipped: `dist/plugin` carries agents, review and skills.
The enforced rules travel regardless -- the code does what they say -- but the guidance
rules are the ones no gate can hold up, so an install that never receives them simply does
not follow them. They used to ship as skill text; the dissolutions took that away.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from integrations.compiler.agents_md import _rules_section, build_agents_md

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_YAML = REPO_ROOT / "canonical" / "rules.yml"


@pytest.fixture(scope="module")
def projection() -> str:
    return build_agents_md()


def _declared_packs() -> set[str]:
    """Pack ids as an install sees them: the shipped `ds-` name."""
    packs = yaml.safe_load((REPO_ROOT / "packs.yaml").read_text(encoding="utf-8"))["packs"]
    out = set()
    for key, cfg in packs.items():
        skill = (cfg or {}).get("skill", key)
        out.add(skill if skill.startswith("ds-") else f"ds-{skill}")
    return out


# ── every promise resolves ────────────────────────────────────────────────────


def test_no_skill_id_names_a_pack_that_does_not_exist(projection):
    """The defect three dissolutions walked past.

    A `pack:mode` reference in this file is an instruction to invoke something. When the
    pack is gone the instruction does not fail loudly -- the agent goes looking, finds
    nothing, and improvises.
    """
    declared = _declared_packs()
    referenced = set(re.findall(r"`(ds-[a-z0-9-]+):[a-z-]+`", projection))
    phantom = sorted(r for r in referenced if r not in declared)
    assert not phantom, (
        "the operator projection tells an install to invoke skills that no pack provides: "
        f"{phantom}"
    )


def test_the_operating_loop_names_commands_not_internal_functions(projection):
    """Route work through `ds`, which is the operator's standing rule.

    `get_project_state()`, `mark_task_done(...)` and `close_work_order(...)` are internals.
    An install told to call them is told to import the engine, which is the habit that let
    three capabilities exist with no CLI door at all.
    """
    start = projection.index("## Authority & Operating Rules")
    nxt = projection.find("\n## ", start + 1)
    end = nxt if nxt != -1 else len(projection)
    block = projection[start:end]
    calls = sorted(set(re.findall(r"`([a-z_]+\([^`]*\))`", block)))
    assert not calls, f"the operating loop names internal functions instead of commands: {calls}"
    assert "ds work-order start" in block
    assert "ds work-order close" in block
    assert "ds project state" in block


def test_every_ds_command_the_loop_names_is_a_real_command(projection):
    """A command that does not parse is the same defect as a skill that does not exist,
    one layer over. This resolves each against the real parser tree."""
    from interfaces.cli.ds import build_parser

    start = projection.index("## Authority & Operating Rules")
    nxt = projection.find("\n## ", start + 1)
    end = nxt if nxt != -1 else len(projection)
    block = projection[start:end]

    parser = build_parser()
    top = next(a for a in parser._actions if a.dest == "command")

    missing = []
    for phrase in sorted(set(re.findall(r"`ds ([a-z-]+(?: [a-z-]+)?)", block))):
        parts = phrase.split()
        group = top.choices.get(parts[0])
        if group is None:
            missing.append(f"ds {phrase}")
            continue
        if len(parts) > 1:
            sub = next(
                (
                    a
                    for a in group._actions
                    if getattr(a, "choices", None) and parts[1] in a.choices
                ),
                None,
            )
            if sub is None:
                missing.append(f"ds {phrase}")
    assert not missing, f"the operating loop names commands that do not exist: {missing}"


# ── the guidance rules travel ─────────────────────────────────────────────────


def test_every_guidance_rule_reaches_the_projection(projection):
    """The half no gate can enforce is the half that has to be read.

    Checked against the registry rather than a pinned count, so a rule declared guidance
    tomorrow is carried without anyone remembering to edit this file.
    """
    registry = yaml.safe_load(RULES_YAML.read_text(encoding="utf-8"))
    guidance = [r for r in registry["rules"] if r.get("guidance") is True]
    assert guidance, "no guidance rules in the registry; has the schema changed?"

    missing = [r["id"] for r in guidance if " ".join(str(r["statement"]).split()) not in projection]
    assert not missing, f"guidance rules that no install would ever receive: {missing}"


def test_enforced_rules_are_not_projected(projection):
    """Shipping all 56 would put the registry in every session's context to restate what
    the code already does -- the cost the dissolution exists to remove. An enforced rule
    does not need reading: the gate refuses and names what objected."""
    registry = yaml.safe_load(RULES_YAML.read_text(encoding="utf-8"))
    enforced = [r for r in registry["rules"] if r.get("enforced_by")]
    leaked = [r["id"] for r in enforced if " ".join(str(r["statement"]).split()) in projection]
    assert not leaked, f"enforced rules were projected as if unenforced: {leaked}"


def test_the_section_says_these_are_the_unenforced_ones(projection):
    """A list of rules with no frame reads as "the rules", which would leave an agent
    thinking the enforced ones do not apply."""
    assert "## Operating Rules" in projection
    assert "nothing enforces" in projection


def test_an_unreadable_registry_yields_no_section_rather_than_an_empty_one(tmp_path):
    """A heading over an empty list reads as "there are no rules", which is worse than
    the section being absent and noticed."""
    assert _rules_section(tmp_path / "does-not-exist.yml") == ""

    empty = tmp_path / "empty.yml"
    empty.write_text("version: 1\nrules: []\n", encoding="utf-8")
    assert _rules_section(empty) == ""

    none_guidance = tmp_path / "enforced-only.yml"
    none_guidance.write_text(
        "version: 1\nrules:\n  - id: x\n    statement: A thing.\n"
        "    source: nowhere.py\n    enforced_by: [canonical/rules.yml]\n",
        encoding="utf-8",
    )
    assert _rules_section(none_guidance) == ""
