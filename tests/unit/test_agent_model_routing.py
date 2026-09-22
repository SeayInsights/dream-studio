"""Every bundled subagent must declare the model it runs on.

CLAUDE.md has carried a model-routing rule for a long time ("Haiku for
searches/exploration subagents; Sonnet for code-change subagents"). Over 118
days of telemetry it was followed 0% of the time: 91% of token spend landed on
the Opus tier and Haiku was never invoked once.

The reason is mechanical, not cultural. All nine agents in canonical/agents/
shipped with no `model:` in their frontmatter, so every one of them inherited
the caller's model — which is Opus. The rule lived in prose, and prose is not a
dispatch decision. control/execution/models/selector.py computes a tier
recommendation, but nothing consumes its return value either.

Agent frontmatter IS consumed — the installer copies these files verbatim into
the Claude Code config root, and the harness reads `model:` when dispatching.
So it is the one place the routing rule can be made binding, and this test keeps
it that way: a new agent with no declared model fails here rather than silently
costing Opus rates forever.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
AGENTS_DIR = REPO_ROOT / "canonical" / "agents"

# Aliases the Claude Code harness resolves to a current model. A concrete id
# (claude-sonnet-5) is also legal but pins the agent to one generation, so it
# needs a deliberate choice rather than a default.
ALLOWED_ALIASES = frozenset({"haiku", "sonnet", "opus", "inherit"})

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def _agent_files() -> list[Path]:
    return [p for p in sorted(AGENTS_DIR.glob("*.md")) if p.stem != "README"]


def _frontmatter(path: Path) -> dict[str, str]:
    m = _FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


def test_agents_directory_is_populated():
    """Guard the guard — an empty glob would make every check below vacuous."""
    assert _agent_files(), f"no agent files found under {AGENTS_DIR}"


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.stem)
def test_agent_declares_a_model(path: Path):
    """No agent may inherit its model by omission."""
    fm = _frontmatter(path)
    assert fm, f"{path.name} has no parseable frontmatter"

    model = fm.get("model")
    assert model, (
        f"{path.name} declares no `model:`. It will inherit the caller's model, "
        "which is how 91% of spend ended up on the Opus tier. Add "
        "`model: haiku|sonnet|opus` to the frontmatter."
    )
    assert model in ALLOWED_ALIASES or model.startswith("claude-"), (
        f"{path.name} declares model: {model!r}, which is neither an alias "
        f"({sorted(ALLOWED_ALIASES)}) nor a concrete claude-* id"
    )


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.stem)
def test_agent_frontmatter_has_name_and_description(path: Path):
    fm = _frontmatter(path)
    assert (
        fm.get("name") == path.stem
    ), f"{path.name}: frontmatter name {fm.get('name')!r} must match the filename"
    assert fm.get("description"), f"{path.name}: description is required for routing"


def test_not_every_agent_is_opus():
    """A blanket `model: opus` would satisfy the check above while changing nothing."""
    models = {p.stem: _frontmatter(p).get("model") for p in _agent_files()}
    non_opus = {k: v for k, v in models.items() if v != "opus"}
    assert non_opus, (
        "every agent is pinned to opus, which reproduces the exact spend profile "
        f"this guard exists to change: {models}"
    )


# ---------------------------------------------------------------------------------------
# An agent's domain knowledge must BE in the agent, not be named by it.
#
# These files used to end with "your full set of patterns, anti-patterns, gotchas, commands
# and version notes is in ~/.claude/skills/<file>. Read it completely before responding."
# That is an instruction, not a mechanism: nothing makes a subagent read the file, and when
# it does not the answer comes from general knowledge -- fluent, confident, and
# indistinguishable from a good one. Every agent also carried a paragraph beginning "If the
# skill file is unavailable", which is the authors recording that they knew it was
# unreliable.
#
# The skill is now inlined at build time by integrations/compiler/agents.py. These tests
# hold that: the knowledge is present, it matches the skill it came from, and the old
# pointer form has not crept back.
# ---------------------------------------------------------------------------------------

SHIPPED_SKILLS = REPO_ROOT / "dist" / "plugin" / "skills"

_POINTER_RE = re.compile(r"~/\.claude/skills/[A-Za-z0-9_./-]+\.md")


def _meta_files() -> list[Path]:
    return sorted(AGENTS_DIR.glob("*.meta.yml"))


def test_every_agent_has_a_declaration_to_compile_from():
    """Guard the guard: the checks below iterate declarations, and an empty glob would
    make all of them vacuous."""
    metas = {p.name[: -len(".meta.yml")] for p in _meta_files()}
    agents = {p.stem for p in _agent_files()}
    assert metas, f"no .meta.yml declarations under {AGENTS_DIR}"
    assert metas == agents, f"declarations and agents disagree: {metas ^ agents}"


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.stem)
def test_the_agent_carries_its_knowledge_rather_than_a_pointer_to_it(path: Path):
    """The whole point. A subagent that has to fetch its own knowledge is one that can
    answer without it, and nothing downstream can tell the difference."""
    import yaml

    body = path.read_text(encoding="utf-8")
    assert not _POINTER_RE.search(body), (
        f"{path.name} names a skill file instead of carrying it. The pointer form is what "
        "this compiler replaced -- regenerate with "
        "`py -m integrations.compiler.agents --write`."
    )

    meta = yaml.safe_load((AGENTS_DIR / f"{path.stem}.meta.yml").read_text(encoding="utf-8"))
    skill = SHIPPED_SKILLS / meta["skill"]
    assert skill.is_file(), f"{path.stem}: declared skill {meta['skill']} is not shipped"

    knowledge = skill.read_text(encoding="utf-8").strip()
    assert knowledge in body, (
        f"{path.name} does not contain the text of {meta['skill']}. It is stale -- "
        "regenerate with `py -m integrations.compiler.agents --write`."
    )


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.stem)
def test_the_agent_states_what_it_returns(path: Path):
    """A subagent's report is the only thing that survives it. If the shape is not fixed,
    the skill that dispatched it cannot rely on what comes back."""
    body = path.read_text(encoding="utf-8")
    assert "## What you return" in body, f"{path.name} declares no output contract"


def test_the_agents_match_their_declarations():
    """The drift half. A skill edit that is not recompiled leaves agents carrying old
    knowledge, silently -- which is the failure the pointer form had, relocated."""
    from integrations.compiler.agents import check

    stale = check()
    assert not stale, (
        f"{len(stale)} agent(s) no longer match what their declaration compiles to: "
        f"{', '.join(stale)}. Run `py -m integrations.compiler.agents --write`."
    )


def test_the_shipped_skills_tree_is_there_at_all():
    """Guard the guard: if dist/plugin/skills were missing, every check above would fail
    for the wrong reason and the message would send someone after the agents."""
    assert SHIPPED_SKILLS.is_dir(), (
        f"{SHIPPED_SKILLS} does not exist -- regenerate the plugin before reading this "
        "file's failures as an agent problem."
    )
