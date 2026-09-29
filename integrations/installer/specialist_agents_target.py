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

from integrations.compiler.reviewers import AGENTS_DIR, PREFIX
from integrations.targets.registry import (
    get_target_spec,
    specialist_agents_target_path,
    translate_model,
)

_MODEL_LINE_RE = re.compile(r"^model: (.+)$", re.MULTILINE)


def reviewer_files() -> list[Path]:
    """Every compiled reviewer, in the order `sorted()` gives -- not install order,
    just a stable one so a dry-run plan and a real install name files the same way."""
    return sorted(AGENTS_DIR.glob(f"{PREFIX}*.md"))


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
    ) -> None:
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

    def plan(self) -> dict[str, Any]:
        """Dry-run description of what install would do."""
        return {
            "tool_id": self.tool_id,
            "target_dir": str(self.target_dir),
            "files": [f.name for f in reviewer_files()],
        }

    def install(self, mode: Literal["dry_run", "execute"]) -> dict[str, Any]:
        files = reviewer_files()
        result: dict[str, Any] = {
            "tool_id": self.tool_id,
            "mode": mode,
            "target_dir": str(self.target_dir),
            "written": [],
        }
        if mode != "execute":
            return result
        self.target_dir.mkdir(parents=True, exist_ok=True)
        for src in files:
            translated = translate_reviewer_body(src.read_text(encoding="utf-8"), self.tool_id)
            (self.target_dir / src.name).write_text(translated, encoding="utf-8")
            result["written"].append(src.name)
        return result
