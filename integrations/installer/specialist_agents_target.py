"""Install the round table's compiled reviewer agents onto a non-Claude specialist target.

The compiled reviewers (`canonical/agents/review-*.md`, from `integrations.compiler.
reviewers`) carry no Claude-specific content at all -- the contract tells the reviewer to
run `ds review --run ...`, a tool-agnostic CLI command, and every lane's question,
signature, precedent and standard came from `canonical/review_lanes.yml`. The one line
that IS tool-specific is `model:`, holding Dream Studio's own canonical alias (haiku,
sonnet, opus, or inherit -- see `scripts/seat_lanes_data.py`'s SEAT_MODELS).

So this installer does not recompile anything. It copies the SAME file, translating only
that one line through `integrations.targets.registry.translate_model()` -- the seat's
question and this tool's model both come from one place each, and neither drifts from
the Claude Code copy by hand.

Scoped to the round table's reviewers specifically (the `review-` prefix), not Dream
Studio's ~45 domain specialists -- a natural future extension, not this one's job.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from integrations.compiler.reviewers import resolve_agent_names, reviewer_files
from integrations.targets.registry import (
    get_target_spec,
    specialist_agents_target_path,
    translate_model,
)

_MODEL_LINE_RE = re.compile(r"^model: (.+)$", re.MULTILINE)


def translate_reviewer_body(body: str, tool_id: str) -> str:
    """The same file, with its one tool-specific line translated.

    Raises if there is no `model:` line to translate (a compiled reviewer with no model
    is a bug in the compiler, not something to install around) or if `translate_model`
    refuses the file's own alias for this tool -- both cases mean installing verbatim
    would ship a model string nobody chose, or none at all.
    """
    match = _MODEL_LINE_RE.search(body)
    if not match:
        raise ValueError("no `model:` line found in this reviewer's frontmatter to translate")
    alias = match.group(1).strip()
    translated = translate_model(tool_id, alias)
    return _MODEL_LINE_RE.sub(f"model: {translated}", body, count=1)


class SpecialistAgentsInstaller:
    """Install every compiled reviewer onto one `md_frontmatter`-format target."""

    def __init__(
        self,
        tool_id: str,
        *,
        project_root: Path,
        home: Path | None = None,
        agents: list[str] | None = None,
    ) -> None:
        """*agents*, if given, installs only that subset (each entry a seat name or an
        agent slug -- see `resolve_agent_names`) rather than every compiled reviewer.
        Without it, this tool gets all nine; installing a different subset onto a
        second tool is what makes a genuinely mixed roster (nine seats on Claude, one
        on Codex) reachable, rather than every target getting the whole bench or
        nothing.
        """
        spec = get_target_spec(tool_id)
        if spec.specialist_agent_format != "md_frontmatter":
            raise ValueError(
                f"{tool_id}: specialist_agent_format is"
                f" {spec.specialist_agent_format!r}, not 'md_frontmatter' -- this"
                " installer only handles that shape (codex's TOML format needs its own)"
            )
        self.tool_id = tool_id
        self.project_root = Path(project_root)
        self.home = Path(home) if home is not None else Path.home()
        self.target_dir = specialist_agents_target_path(
            tool_id, project_root=self.project_root, home=self.home
        )
        self._files = resolve_agent_names(agents) if agents is not None else reviewer_files()

    def plan(self) -> dict[str, Any]:
        """Dry-run description of what install would do. Delegates to install() rather
        than keeping a second copy of "which files, which target" -- see the same
        choice made the same way in install() itself."""
        return self.install("dry_run")

    def install(self, mode: Literal["dry_run", "execute"]) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tool_id": self.tool_id,
            "mode": mode,
            "target_dir": str(self.target_dir),
            # ALWAYS POPULATED, dry_run included. A dry-run that reports only
            # written: [] tells a caller nothing beyond "nothing happened, which is
            # what dry-run means" -- it does not answer the actual question a dry-run
            # exists to answer, "what WOULD happen". `files` is that answer; `written`
            # stays the record of what this call actually did.
            "files": [f.name for f in self._files],
            "written": [],
        }
        if mode != "execute":
            return result
        self.target_dir.mkdir(parents=True, exist_ok=True)
        for src in self._files:
            translated = translate_reviewer_body(src.read_text(encoding="utf-8"), self.tool_id)
            (self.target_dir / src.name).write_text(translated, encoding="utf-8")
            result["written"].append(src.name)
        return result
