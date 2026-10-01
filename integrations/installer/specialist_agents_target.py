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

from pathlib import Path
from typing import Any, Literal

from integrations.compiler.reviewers import (
    MODEL_LINE_RE,
    project_reviewer_files,
    resolve_agent_names,
    resolve_seat_assignment,
    reviewer_files,
    seat_name_for_file,
    set_model_alias,
)
from integrations.targets.registry import (
    get_target_spec,
    specialist_agents_target_path,
    translate_model,
)


def translate_reviewer_body(
    body: str, tool_id: str, *, model_alias_override: str | None = None
) -> str:
    """The same file, with its one tool-specific line translated.

    *model_alias_override*, when given (a pinned seat's own model -- see
    `core.config.seat_providers`), replaces the file's own baked-in alias rather than
    reading it from the frontmatter -- the pin's whole point.

    Raises if there is no `model:` line to translate (a compiled reviewer with no model
    is a bug in the compiler, not something to install around) or if `translate_model`
    refuses the alias for this tool -- both cases mean installing verbatim would ship a
    model string nobody chose, or none at all.
    """
    match = MODEL_LINE_RE.search(body)
    if not match:
        raise ValueError("no `model:` line found in this reviewer's frontmatter to translate")
    alias = model_alias_override if model_alias_override is not None else match.group(1).strip()
    translated = translate_model(tool_id, alias)
    return set_model_alias(body, translated)


class SpecialistAgentsInstaller:
    """Install every compiled reviewer onto one `md_frontmatter`-format target."""

    def __init__(
        self,
        tool_id: str,
        *,
        project_root: Path,
        home: Path | None = None,
        agents: list[str] | None = None,
        scope: str | None = None,
    ) -> None:
        """*agents*, if given, installs only that subset (each entry a seat name or an
        agent slug -- see `resolve_agent_names`) rather than every compiled reviewer.
        Without it, this tool gets all nine plus *project_root*'s own seats, if it has
        a `.ds-review-lanes.yml` marker (see `project_reviewer_files`); installing a
        different subset onto a second tool is what makes a genuinely mixed roster
        (nine seats on Claude, one on Codex) reachable, rather than every target
        getting the whole bench or nothing.

        *scope*, if given, overrides this tool's default scope -- raises if the tool
        does not support it (see `integrations.targets.registry.resolve_scope`).
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
            tool_id, project_root=self.project_root, home=self.home, scope=scope
        )
        # Whether THIS call named its seats explicitly -- governs whether a seat
        # pinned to a different provider (core.config.seat_providers) gets skipped
        # here or honored anyway. See install()'s per-file loop.
        self._explicit = agents is not None
        if agents is not None:
            self._files = resolve_agent_names(agents, repo_root=self.project_root)
        else:
            self._files = reviewer_files() + project_reviewer_files(self.project_root)

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
            # Every candidate pinned (core.config.seat_providers) to a DIFFERENT
            # provider than self.tool_id, skipped here because this call named no
            # explicit --agents -- the "install everything" default routes a pinned
            # seat to its own provider instead of installing it twice under two
            # names. An explicit --agents request for the same seat is honored
            # anyway (see the loop below); it names this exact tool for this exact
            # seat, a stronger signal than the standing pin.
            "skipped": [],
        }
        if mode == "execute":
            self.target_dir.mkdir(parents=True, exist_ok=True)
        for src in self._files:
            seat = seat_name_for_file(src, repo_root=self.project_root)
            provider, model_override, _effort_override = resolve_seat_assignment(seat, self.tool_id)
            if provider != self.tool_id and not self._explicit:
                result["skipped"].append({"seat": seat, "file": src.name, "pinned_to": provider})
                continue
            if mode != "execute":
                continue
            translated = translate_reviewer_body(
                src.read_text(encoding="utf-8"), self.tool_id, model_alias_override=model_override
            )
            (self.target_dir / src.name).write_text(translated, encoding="utf-8")
            result["written"].append(src.name)
        return result
