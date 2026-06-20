"""Generic AGENTS.md installer for native-AGENTS.md tools (Phase 20).

Places the generated universal AGENTS.md at the tool's expected location. Unlike
ClaudeCodeInstaller this installs no hooks (Claude-Code-only) and no skills — these
tools read AGENTS.md directly. MCP install is left to the tool's own config and is
only advertised via the target spec (we do not fabricate unverified MCP formats).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from integrations.compiler.agents_md import build_agents_md
from integrations.targets.registry import agents_md_target_path, get_target_spec


class AgentsTargetInstaller:
    """Install the generated AGENTS.md for a single non-Claude target."""

    def __init__(
        self,
        tool_id: str,
        *,
        project_root: Path,
        home: Path | None = None,
        canonical_root: Path | None = None,
    ) -> None:
        self.spec = get_target_spec(tool_id)
        self.tool_id = tool_id
        self.project_root = Path(project_root)
        self.home = Path(home) if home is not None else Path.home()
        self.canonical_root = canonical_root
        self.target_path = agents_md_target_path(
            tool_id, project_root=self.project_root, home=self.home
        )

    def _content(self) -> str:
        if self.canonical_root is not None:
            return build_agents_md(canonical_root=self.canonical_root)
        return build_agents_md()

    def plan(self) -> dict[str, Any]:
        """Dry-run description of what install would do."""
        return {
            "tool_id": self.tool_id,
            "display_name": self.spec.display_name,
            "scope": self.spec.scope,
            "agents_md_path": str(self.target_path),
            "installs_hooks": self.spec.supports_hooks,
            "mcp_supported": self.spec.supports_mcp,
        }

    def install(self, mode: Literal["dry_run", "execute"]) -> dict[str, Any]:
        """Write AGENTS.md (execute) or just report the plan (dry_run)."""
        result: dict[str, Any] = {
            "tool_id": self.tool_id,
            "mode": mode,
            "agents_md_path": str(self.target_path),
            "written": False,
        }
        if mode == "execute":
            self.target_path.parent.mkdir(parents=True, exist_ok=True)
            self.target_path.write_text(self._content(), encoding="utf-8")
            result["written"] = True
        return result
