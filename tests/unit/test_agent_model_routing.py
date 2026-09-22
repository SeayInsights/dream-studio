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
# An agent IS its skill pointer. If that breaks, the agent still dispatches -- it just has
# no knowledge, and says so to the user instead of to anyone who could fix it.
# ---------------------------------------------------------------------------------------

#: What an installed agent actually reads. The installer copies these files verbatim into
#: the Claude Code config root, so the path in the body is resolved against the SHIPPED
#: plugin, not against canonical -- checking canonical would pass on a projection that
#: never got regenerated.
SHIPPED_SKILLS = REPO_ROOT / "dist" / "plugin" / "skills"

_SKILL_POINTER_RE = re.compile(r"~/\.claude/skills/([A-Za-z0-9_./-]+\.md)")


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.stem)
def test_agent_points_at_a_skill_file_that_exists(path: Path):
    """The agent bodies are all the same shape: a persona, then "your full set of patterns,
    anti-patterns, gotchas, commands and version notes is in <file>. Read it completely
    before responding."

    So the pointer is not a reference, it is the entire payload. A rename on the skill side
    leaves the agent dispatchable and empty, and the failure surfaces as a vaguer answer
    rather than as an error -- which is the same shape as the fourteen instructions that
    named a linter nobody had committed.
    """
    body = path.read_text(encoding="utf-8")
    refs = _SKILL_POINTER_RE.findall(body)
    assert refs, (
        f"{path.name} names no skill file. These agents carry no domain knowledge of their "
        "own -- the pointer is the payload, so an agent without one is a persona and "
        "nothing else."
    )
    for ref in refs:
        target = SHIPPED_SKILLS / ref
        assert target.is_file(), (
            f"{path.name} tells the agent to read ~/.claude/skills/{ref}, which is not in "
            f"the shipped plugin. The agent would dispatch and have nothing to read. "
            f"Either the skill moved, or dist/plugin needs regenerating."
        )
        assert target.stat().st_size > 200, (
            f"{path.name} points at {ref}, which exists but is {target.stat().st_size} "
            "bytes -- too small to be the knowledge the agent is told to read completely."
        )


def test_the_shipped_skills_tree_is_there_at_all():
    """Guard the guard: if dist/plugin/skills were missing, every check above would fail
    for the wrong reason and the message would send someone after the agents."""
    assert SHIPPED_SKILLS.is_dir(), (
        f"{SHIPPED_SKILLS} does not exist -- regenerate the plugin before reading this "
        "file's failures as an agent problem."
    )
