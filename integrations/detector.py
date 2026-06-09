"""Tool detection — locates AI tool config roots for integration provisioning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CLAUDE_CODE_TOOL_ID = "claude_code"
SUPPORTED_TOOLS = (CLAUDE_CODE_TOOL_ID,)


@dataclass
class DetectedTool:
    tool_id: str
    scope: str  # "user" or "project"
    config_root: Path


def _infer_scope(working_dir: Path) -> str:
    """Infer scope: project if .claude/ exists in working_dir, else user."""
    if (working_dir / ".claude").is_dir():
        return "project"
    return "user"


def detect_claude_code(
    *,
    working_dir: Path | None = None,
    scope_override: str | None = None,
) -> DetectedTool:
    """Return detection result for Claude Code.

    Does not require config_root to exist — caller checks health state via doctor().
    """
    cwd = working_dir or Path.cwd()
    scope = scope_override if scope_override in ("user", "project") else _infer_scope(cwd)

    if scope == "project":
        config_root = cwd / ".claude"
    else:
        config_root = Path.home() / ".claude"

    return DetectedTool(tool_id=CLAUDE_CODE_TOOL_ID, scope=scope, config_root=config_root)


def detect_all(*, working_dir: Path | None = None) -> list[DetectedTool]:
    """Return detected tools for all supported targets."""
    return [detect_claude_code(working_dir=working_dir)]
