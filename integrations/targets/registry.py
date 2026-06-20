"""Per-tool integration target registry (Phase 20, WO-P20-TOOL-TARGETS).

Dream Studio installs onto any tool that reads AGENTS.md. Each target declares
*where* AGENTS.md belongs for that tool and which extras it supports. Hooks are
Claude-Code-only; MCP is supported where the tool has a documented MCP config.

The generic AgentsTargetInstaller consumes these specs to place the generated
AGENTS.md (from integrations.compiler.agents_md) in the right location.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Scope = Literal["project", "user"]


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
    ),
    "gemini_cli": TargetSpec(
        tool_id="gemini_cli",
        display_name="Gemini CLI",
        scope="project",
        agents_md_relpath="AGENTS.md",
        supports_mcp=True,
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
