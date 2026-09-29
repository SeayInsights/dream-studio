"""Install the round table's compiled reviewer agents onto Codex CLI.

Codex's specialist-agent format is structurally different from Claude Code's,
Gemini CLI's and Cursor's shared markdown-plus-frontmatter shape (see
`specialist_agents_target.py` for those): a standalone TOML file per agent, with a
`developer_instructions` string standing in for the markdown body. Same source content
(`canonical/agents/review-*.md`), same one translated field (`model`), different
container -- this module is what building that container looks like, not a second
compiler. No third-party TOML writer: the schema this needs is four flat string/scalar
keys, well within what a few lines of correct escaping cover, and Dream Studio's own
convention is to own a mechanism this narrow rather than take a dependency for it.
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

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n\n?(.*)\Z", re.S)
_MODEL_LINE_RE = re.compile(r"^model: (.+)$", re.MULTILINE)


def reviewer_files() -> list[Path]:
    return sorted(AGENTS_DIR.glob(f"{PREFIX}*.md"))


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """The compiled file's own two parts: its flat frontmatter and everything after it.

    Reused rather than re-derived from scratch: `integrations.compiler.reviewers.
    build_reviewer` writes exactly this shape (a flat `key: value` block, one blank
    line, then the body), so parsing it back out is the inverse of a known writer, not
    a guess at an unspecified one.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("not a `---\\n...\\n---\\n` frontmatter file")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields, match.group(2)


def _toml_basic_string(value: str) -> str:
    """A TOML basic string (`"..."`) for a single-line field. `name` and `description`
    are both compiler-generated single lines (see `_describe`/`_slug`); this still
    escapes backslash and quote properly rather than assuming neither appears."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_literal_multiline(value: str) -> str:
    """A TOML multi-line LITERAL string (`'''...'''`) for the body. Literal, not basic,
    on purpose: the body is markdown carrying backslashes (regex, Windows paths) and
    double quotes throughout its lane content, and a literal string applies no escape
    processing to any of that -- nothing to get wrong across hundreds of lines. Its one
    restriction is that the content cannot itself contain `'''`; raising on that rather
    than attempting the spec's own escape-hatch keeps this a narrow, correct mechanism
    instead of a general one.
    """
    if "'''" in value:
        raise ValueError(
            "developer_instructions body contains a literal ''' sequence, which a TOML"
            " multi-line literal string cannot carry -- this compiled reviewer needs a"
            " different quoting strategy, not a silent corruption of its content"
        )
    return f"'''\n{value}'''"


def codex_toml_for_reviewer(body: str) -> str:
    """The compiled reviewer's own markdown file, as a Codex custom-agent TOML file.

    `body` is the source .md file's full text (frontmatter and all) -- so a caller can
    translate straight from `Path.read_text()`, the same interface
    `translate_reviewer_body` (the md_frontmatter installer's sibling) already uses.
    """
    fields, instructions = _split_frontmatter(body)
    for required in ("name", "description"):
        if not fields.get(required):
            raise ValueError(f"reviewer frontmatter has no `{required}`")
    alias = fields.get("model", "").strip()
    if not alias:
        raise ValueError("reviewer frontmatter has no `model` to translate")
    model = translate_model("codex", alias)

    lines = [
        f"name = {_toml_basic_string(fields['name'])}",
        f"description = {_toml_basic_string(fields['description'])}",
        f"model = {_toml_basic_string(model)}",
        f"developer_instructions = {_toml_literal_multiline(instructions)}",
    ]
    return "\n".join(lines) + "\n"


class CodexAgentsInstaller:
    """Install every compiled reviewer onto Codex CLI, as TOML."""

    def __init__(self, *, project_root: Path, home: Path | None = None) -> None:
        spec = get_target_spec("codex")
        if spec.specialist_agent_format != "toml":
            raise ValueError(
                f"codex: specialist_agent_format is {spec.specialist_agent_format!r},"
                " not 'toml' -- this installer only handles that shape"
            )
        self.project_root = Path(project_root)
        self.home = Path(home) if home is not None else Path.home()
        self.target_dir = specialist_agents_target_path(
            "codex", project_root=self.project_root, home=self.home
        )

    def plan(self) -> dict[str, Any]:
        return {
            "tool_id": "codex",
            "target_dir": str(self.target_dir),
            "files": [f"{f.stem}.toml" for f in reviewer_files()],
        }

    def install(self, mode: Literal["dry_run", "execute"]) -> dict[str, Any]:
        files = reviewer_files()
        result: dict[str, Any] = {
            "tool_id": "codex",
            "mode": mode,
            "target_dir": str(self.target_dir),
            "written": [],
        }
        if mode != "execute":
            return result
        self.target_dir.mkdir(parents=True, exist_ok=True)
        for src in files:
            toml_text = codex_toml_for_reviewer(src.read_text(encoding="utf-8"))
            out_name = f"{src.stem}.toml"
            (self.target_dir / out_name).write_text(toml_text, encoding="utf-8")
            result["written"].append(out_name)
        return result
