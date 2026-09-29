"""Per-tool specialist-agent dispatch: format, path, and model translation.

Dream Studio's round table (`canonical/review_lanes.yml`) compiles one reviewer per
seat, dispatched with a model chosen for that seat (see
`tests/unit/test_reviewer_model_routing.py`). That reviewer only ever reached Claude
Code -- the other tools Dream Studio installs onto (codex, gemini_cli, windsurf, aider,
cursor) had no declared capability to host a specialist agent at all, and no mapping
from Dream Studio's own haiku/sonnet/opus/inherit vocabulary to any of their real model
catalogs. codex, gemini_cli and cursor are verified (2026-09, against each tool's own
docs) to have a specialist-subagent primitive Dream Studio can target; windsurf and
aider are not verified either way and stay undeclared -- that absence is the honest
answer for a tool nobody has confirmed one way or the other, not a gap to fill in
passing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.targets.registry import (
    TARGET_SPECS,
    TargetSpec,
    get_target_spec,
    specialist_agents_target_path,
    translate_model,
)

VERIFIED_SPECIALIST_TOOLS = ("codex", "gemini_cli", "cursor")
UNVERIFIED_TOOLS = ("windsurf", "aider")

#: The three tiers every round-table seat actually resolves to today (see
#: scripts/seat_lanes_data.py's SEAT_MODELS). "inherit" is legal Dream-Studio-wide but
#: not yet used by any seat, so a tool is allowed to leave it unmapped.
LIVE_ALIASES = ("haiku", "sonnet", "opus")


@pytest.mark.parametrize("tool_id", VERIFIED_SPECIALIST_TOOLS)
def test_a_verified_tool_declares_the_full_shape(tool_id):
    spec = get_target_spec(tool_id)
    assert spec.specialist_agent_format in ("md_frontmatter", "toml")
    assert spec.specialist_agents_relpath
    for alias in LIVE_ALIASES:
        assert alias in spec.model_alias_map, f"{tool_id}: no mapping for {alias!r}"
        assert spec.model_alias_map[alias], f"{tool_id}: empty mapping for {alias!r}"


@pytest.mark.parametrize("tool_id", UNVERIFIED_TOOLS)
def test_an_unverified_tool_declares_no_specialist_capability(tool_id):
    """Absence is the honest answer here, not an oversight -- asserted so a future edit
    that quietly adds a guessed mapping for one of these fails a test that says why not
    to, rather than shipping a translation nobody checked against the tool's own docs."""
    spec = get_target_spec(tool_id)
    assert spec.specialist_agent_format is None
    assert spec.model_alias_map == {}


def test_a_spec_declaring_format_without_a_relpath_is_rejected():
    with pytest.raises(ValueError, match="specialist_agents_relpath"):
        TargetSpec(
            tool_id="x",
            display_name="X",
            scope="project",
            agents_md_relpath="AGENTS.md",
            specialist_agent_format="toml",
            model_alias_map={"sonnet": "x-model"},
        )


def test_a_spec_declaring_format_without_a_model_map_is_rejected():
    with pytest.raises(ValueError, match="model_alias_map"):
        TargetSpec(
            tool_id="x",
            display_name="X",
            scope="project",
            agents_md_relpath="AGENTS.md",
            specialist_agent_format="toml",
            specialist_agents_relpath=".x/agents",
        )


def test_a_spec_with_no_format_needs_neither():
    """Guards the guard: the two rejection tests above must not be true unconditionally,
    or every TargetSpec in the real registry would already be failing to construct."""
    TargetSpec(
        tool_id="x",
        display_name="X",
        scope="project",
        agents_md_relpath="AGENTS.md",
    )


@pytest.mark.parametrize("tool_id", VERIFIED_SPECIALIST_TOOLS)
def test_specialist_agents_target_path_resolves_under_the_right_root(tool_id, tmp_path):
    project = tmp_path / "proj"
    home = tmp_path / "home"
    spec = get_target_spec(tool_id)
    got = specialist_agents_target_path(tool_id, project_root=project, home=home)
    base = project if spec.scope == "project" else home
    assert got == (base / spec.specialist_agents_relpath).resolve()


@pytest.mark.parametrize("tool_id", UNVERIFIED_TOOLS)
def test_specialist_agents_target_path_refuses_an_undeclared_tool(tool_id, tmp_path):
    with pytest.raises(ValueError, match="no specialist_agent_format"):
        specialist_agents_target_path(tool_id, project_root=tmp_path)


@pytest.mark.parametrize("tool_id", VERIFIED_SPECIALIST_TOOLS)
@pytest.mark.parametrize("alias", LIVE_ALIASES)
def test_translate_model_returns_a_real_looking_id_for_every_live_alias(tool_id, alias):
    got = translate_model(tool_id, alias)
    assert got and got.strip() == got, f"{tool_id}/{alias}: {got!r}"


def test_translate_model_refuses_an_alias_the_tool_never_declared():
    with pytest.raises(KeyError, match="no mapping"):
        translate_model("codex", "inherit")


def test_translate_model_refuses_a_tool_with_no_specialist_capability():
    with pytest.raises(ValueError, match="no specialist_agent_format"):
        translate_model("aider", "sonnet")


def test_translate_model_refuses_an_unknown_tool():
    with pytest.raises(KeyError, match="Unknown target"):
        translate_model("not-a-real-tool", "sonnet")


def test_windsurf_and_aider_are_the_only_undeclared_targets():
    """Names the exact set so an operator (or a future PR) can see at a glance which
    tools are pending research rather than have to diff the whole registry to find out."""
    undeclared = {
        tool_id for tool_id, spec in TARGET_SPECS.items() if spec.specialist_agent_format is None
    }
    assert undeclared == set(UNVERIFIED_TOOLS)
