"""Per-tool integration target registry (Phase 20, WO-P20-TOOL-TARGETS).

Dream Studio installs onto any tool that reads AGENTS.md. Each target declares
*where* AGENTS.md belongs for that tool and which extras it supports. Hooks are
Claude-Code-only; MCP is supported where the tool has a documented MCP config.

The generic AgentsTargetInstaller consumes these specs to place the generated
AGENTS.md (from integrations.compiler.agents_md) in the right location.

SPECIALIST-AGENT DISPATCH IS A SEPARATE CAPABILITY FROM AGENTS.MD, added here for the
round table's compiled reviewer seats (`canonical/review_lanes.yml`, `integrations/
compiler/reviewers.py`). AGENTS.md is prose every one of these tools can read; a
specialist agent is a named, independently-dispatched sub-agent with its own model,
which not every tool has a primitive for. Verified against each tool's own current docs
before being declared here (2026-09) -- codex.chatgpt.com's subagents page, geminicli.com's
subagents docs, cursor.com's subagents docs -- rather than assumed from the AGENTS.md
convention alone. `specialist_agent_format=None` is the honest default for a tool with no
such primitive (or one not yet researched), matching `canonical/agents/coverage.yml`'s
`no_agent: <reason>` convention: undeclared is a fact to state, not an omission to fix
opportunistically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Scope = Literal["project", "user"]

#: Dream Studio's own vocabulary for a seat's reasoning tier -- the same set
#: `integrations/compiler/agents.py`'s ALLOWED_MODEL_ALIASES declares for Claude Code
#: (plus a concrete `claude-*` id, which no other tool's map needs to carry since it is
#: Claude-specific by construction). A tool's `model_alias_map` translates each of these
#: into whatever string that tool's own subagent config actually accepts.
CanonicalModelAlias = Literal["haiku", "sonnet", "opus", "inherit"]

#: The subagent config shape a tool accepts, or None when it has none Dream Studio can
#: target. "md_frontmatter" is Markdown with a YAML frontmatter block carrying `model:`
#: -- Claude Code's own shape, and (verified 2026-09) Gemini CLI's and Cursor's as well.
#: "toml" is Codex CLI's -- a standalone TOML file with a `developer_instructions` string
#: field standing in for the markdown body, and its own `model` vocabulary.
SpecialistAgentFormat = Literal["md_frontmatter", "toml"]


@dataclass(frozen=True)
class TargetSpec:
    """How a tool consumes Dream Studio's universal AGENTS.md.

    agents_md_relpath is resolved against the project root (scope="project") or
    the user home (scope="user").
    """

    tool_id: str
    display_name: str
    scope: Scope
    agents_md_relpath: str
    supports_hooks: bool = False
    supports_mcp: bool = False
    #: None (the default) means this tool has no specialist-subagent primitive Dream
    #: Studio targets -- not "not yet gotten to it", a declared fact. See the module
    #: docstring for which tools have actually been verified either way.
    specialist_agent_format: SpecialistAgentFormat | None = None
    #: Where compiled seat agents land, resolved the same way as agents_md_relpath.
    #: Required together with specialist_agent_format -- see __post_init__.
    specialist_agents_relpath: str | None = None
    #: This tool's own model string for each of Dream Studio's canonical aliases.
    #: Required together with specialist_agent_format -- a tool that can host a
    #: specialist agent but has no declared mapping would compile a seat onto a model
    #: string nobody chose, which is the side channel the round table's own per-seat
    #: model field was built to close.
    model_alias_map: dict[CanonicalModelAlias, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.specialist_agent_format is None:
            return
        if not self.specialist_agents_relpath:
            raise ValueError(
                f"{self.tool_id}: declares specialist_agent_format"
                f" {self.specialist_agent_format!r} but no specialist_agents_relpath"
            )
        if not self.model_alias_map:
            raise ValueError(
                f"{self.tool_id}: declares specialist_agent_format"
                f" {self.specialist_agent_format!r} but no model_alias_map -- a seat"
                " would compile onto a model string nobody chose for this tool"
            )


# Native-AGENTS.md tools. Most read AGENTS.md at the project root; Cursor reads
# rule files under ~/.cursor/rules. Claude Code stays in its dedicated installer
# (it additionally installs hooks + skills), so it is intentionally not here.
TARGET_SPECS: dict[str, TargetSpec] = {
    "codex": TargetSpec(
        tool_id="codex",
        display_name="Codex CLI",
        scope="project",
        agents_md_relpath="AGENTS.md",
        supports_mcp=True,
        specialist_agent_format="toml",
        specialist_agents_relpath=".codex/agents",
        # Verified against codex's own subagents/model docs, 2026-09: three real, distinct
        # tiers, not a haiku/sonnet/opus alias worn thin over two. luna is the fast/narrow
        # tier (supports reasoning_effort "none"); sol is the mid default (also supports
        # "none", defaults medium); astra is the most capable, and the only one of the
        # three that CANNOT drop to "none" -- its floor is "low". No "inherit" spawn value
        # was found in codex's own docs, so it is deliberately left unmapped here rather
        # than guessed; translate_model() raises if a seat ever asks for it on this tool.
        model_alias_map={
            "haiku": "gpt-6-luna",
            "sonnet": "gpt-6-sol",
            "opus": "gpt-6-astra",
        },
    ),
    "gemini_cli": TargetSpec(
        tool_id="gemini_cli",
        display_name="Gemini CLI",
        scope="project",
        agents_md_relpath="AGENTS.md",
        supports_mcp=True,
        specialist_agent_format="md_frontmatter",
        specialist_agents_relpath=".gemini/agents",
        # Verified against gemini-cli's own subagents and get-started/gemini-3 docs,
        # 2026-09. The Gemini 3 family currently ships two named tiers, flash and pro --
        # sonnet and opus both land on pro because there is no third, deeper tier to give
        # opus that flash or sonnet do not already have; collapsing them is what the
        # verified catalog supports, not a guess standing in for one. "inherit" is a real,
        # documented literal value here (and the field's own default).
        model_alias_map={
            "haiku": "gemini-3-flash-preview",
            "sonnet": "gemini-3-pro-preview",
            "opus": "gemini-3-pro-preview",
            "inherit": "inherit",
        },
    ),
    "windsurf": TargetSpec(
        tool_id="windsurf",
        display_name="Windsurf",
        scope="project",
        agents_md_relpath="AGENTS.md",
        supports_mcp=True,
    ),
    "aider": TargetSpec(
        tool_id="aider",
        display_name="Aider",
        scope="project",
        agents_md_relpath="AGENTS.md",
        supports_mcp=False,
    ),
    "cursor": TargetSpec(
        tool_id="cursor",
        display_name="Cursor",
        scope="user",
        agents_md_relpath=".cursor/rules/AGENTS.md",
        supports_mcp=True,
        specialist_agent_format="md_frontmatter",
        specialist_agents_relpath=".cursor/agents",
        # Verified against cursor.com/docs/subagents, 2026-09, which shows "claude-opus-5"
        # and "inherit" as literal example model values (default: inherit). Cursor's own
        # short id for the Claude family drops the point-release suffix Anthropic's raw
        # API id carries -- sonnet and haiku follow the same documented pattern by direct
        # analogy to the one tier the docs show verbatim (opus); flagged here because only
        # opus was an exact quoted example, so re-check this pair if Cursor's catalog page
        # ever lists them directly.
        model_alias_map={
            "haiku": "claude-haiku-4-5",
            "sonnet": "claude-sonnet-5",
            "opus": "claude-opus-5",
            "inherit": "inherit",
        },
    ),
}

#: Tool ids handled by the generic AGENTS.md installer (everything but claude_code).
MULTITOOL_IDS: tuple[str, ...] = tuple(TARGET_SPECS.keys())


def get_target_spec(tool_id: str) -> TargetSpec:
    """Return the TargetSpec for *tool_id* or raise KeyError with the valid set."""
    try:
        return TARGET_SPECS[tool_id]
    except KeyError as exc:
        raise KeyError(
            f"Unknown target {tool_id!r}; valid targets: {', '.join(sorted(TARGET_SPECS))}"
        ) from exc


def agents_md_target_path(
    tool_id: str,
    *,
    project_root: Path,
    home: Path | None = None,
) -> Path:
    """Resolve the absolute path where this tool's AGENTS.md belongs."""
    spec = get_target_spec(tool_id)
    base = project_root if spec.scope == "project" else (home or Path.home())
    return (Path(base) / spec.agents_md_relpath).resolve()


def specialist_agents_target_path(
    tool_id: str,
    *,
    project_root: Path,
    home: Path | None = None,
) -> Path:
    """Resolve where this tool's compiled specialist agents belong.

    Raises KeyError (via get_target_spec, for an unknown tool_id) or ValueError for a
    known tool that declares no specialist_agent_format -- there is no path to resolve
    for a capability the tool does not have, and returning one anyway would let a caller
    write files nothing reads.
    """
    spec = get_target_spec(tool_id)
    if spec.specialist_agent_format is None:
        raise ValueError(
            f"{tool_id}: declares no specialist_agent_format -- this tool has no"
            " compiled-specialist-agent target to resolve a path for"
        )
    base = project_root if spec.scope == "project" else (home or Path.home())
    return (Path(base) / spec.specialist_agents_relpath).resolve()


def translate_model(tool_id: str, canonical_alias: str) -> str:
    """This tool's own model string for one of Dream Studio's canonical seat aliases.

    Raises the same way as the rest of this module: an unknown tool_id names the valid
    set (via get_target_spec); a tool with no specialist_agent_format, or one whose
    model_alias_map does not cover this particular alias, raises naming exactly what is
    missing rather than silently returning the alias unchanged -- an untranslated
    "sonnet" handed to a tool that has never heard of it is not a fallback, it is a
    broken install that looks like a working one until the tool rejects it.
    """
    spec = get_target_spec(tool_id)
    if spec.specialist_agent_format is None:
        raise ValueError(f"{tool_id}: has no specialist_agent_format, so no model to translate")
    try:
        return spec.model_alias_map[canonical_alias]
    except KeyError as exc:
        raise KeyError(
            f"{tool_id}: no mapping for canonical model alias {canonical_alias!r};"
            f" this tool declares {sorted(spec.model_alias_map)}"
        ) from exc
