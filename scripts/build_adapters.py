"""Multi-AI adapter build system — generate platform-specific config from SKILL.md sources."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SKILLS_ROOT = _PROJECT_ROOT / "skills"
_TEMPLATES_DIR = _PROJECT_ROOT / "scripts" / "adapter_templates"


def discover_skills() -> list[Path]:
    """Find all SKILL.md files under skills/*/modes/*/SKILL.md.

    Returns sorted list of paths. Skips pack-level SKILL.md files (those are routers, not skills).
    """
    return sorted(_SKILLS_ROOT.glob("*/modes/*/SKILL.md"))


def parse_skill(path: Path) -> dict | None:
    """Extract structured data from a SKILL.md file.

    Returns dict with keys: name, description, pack, triggers, workflow_steps.
    Returns None if the file has no parseable frontmatter.
    """
    content = path.read_text(encoding="utf-8-sig")

    # Parse YAML frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return None

    try:
        fm = yaml.safe_load(fm_match.group(1))
    except yaml.YAMLError:
        return None

    if not isinstance(fm, dict) or "name" not in fm:
        return None

    body = content[fm_match.end():]

    # Extract trigger keywords from description or body
    # Look for patterns like: `keyword:`, `keyword`, or Trigger section
    triggers = []
    # From frontmatter description — extract backtick-quoted keywords
    desc = fm.get("description", "")
    triggers.extend(re.findall(r'`([^`]+)`', desc))

    # From body — look for "## Trigger" section
    trigger_section = re.search(r"## Trigger\s*\n(.*?)(?=\n##|\Z)", body, re.DOTALL)
    if trigger_section:
        triggers.extend(re.findall(r'`([^`]+)`', trigger_section.group(1)))

    # Deduplicate while preserving order
    seen = set()
    unique_triggers = []
    for t in triggers:
        if t not in seen:
            seen.add(t)
            unique_triggers.append(t)

    # Extract numbered workflow steps from body
    workflow_steps = re.findall(r"^\d+\.\s+\*\*(.+?)\*\*", body, re.MULTILINE)
    if not workflow_steps:
        # Try plain numbered list
        workflow_steps = re.findall(r"^\d+\.\s+(.+)$", body, re.MULTILINE)

    return {
        "name": fm.get("name", path.parent.name),
        "description": fm.get("description", ""),
        "pack": fm.get("pack", path.parents[2].name),
        "triggers": unique_triggers,
        "workflow_steps": workflow_steps[:20],  # cap at 20 steps
    }


def load_gotchas(skill_dir: Path) -> list[dict]:
    """Load gotchas.yml avoid entries from a skill directory.

    Returns list of dicts with keys: title, context, fix.
    Returns empty list if file is missing, empty, or malformed.
    """
    gotchas_path = skill_dir / "gotchas.yml"
    if not gotchas_path.is_file():
        return []

    try:
        data = yaml.safe_load(gotchas_path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError:
        return []

    if not isinstance(data, dict):
        return []

    avoid = data.get("avoid", [])
    if not isinstance(avoid, list):
        return []

    return [
        {
            "title": entry.get("title", ""),
            "context": entry.get("context", ""),
            "fix": entry.get("fix", ""),
        }
        for entry in avoid
        if isinstance(entry, dict) and entry.get("title")
    ]


def render_adapter(
    platform_cfg: dict,
    skills: list[dict],
    domains: list[dict] | None = None,
) -> Path:
    """Render a Jinja2 template for a specific platform adapter.

    Args:
        platform_cfg: Platform config dict with keys: template, output_path.
        skills: Parsed skill dicts to inject into the template.
        domains: Optional domain knowledge dicts to inject.

    Returns:
        Path to the written output file.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template(platform_cfg["template"])
    rendered = template.render(skills=skills, domains=domains or [])

    output_path = _PROJECT_ROOT / platform_cfg["output_path"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    return output_path
