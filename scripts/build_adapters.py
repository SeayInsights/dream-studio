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


def load_domains() -> list[dict]:
    """Load domain knowledge files (.md and .yml) from skills/domains/.

    Skips SKILL.md files (pack routers). For .yml files that fail to parse,
    logs an error to stderr and skips the file.

    Returns:
        Sorted list of dicts with keys: name, path, content, type.
    """
    domains_root = _SKILLS_ROOT / "domains"
    if not domains_root.is_dir():
        return []

    results: list[dict] = []

    for pattern in ("**/*.md", "**/*.yml"):
        for filepath in domains_root.glob(pattern):
            if not filepath.is_file():
                continue
            # Skip SKILL.md files — those are routers, not domain knowledge
            if filepath.name == "SKILL.md":
                continue

            content = filepath.read_text(encoding="utf-8-sig")

            # For .yml files, verify valid YAML
            if filepath.suffix == ".yml":
                try:
                    yaml.safe_load(content)
                except yaml.YAMLError as exc:
                    print(f"Warning: skipping malformed YAML {filepath}: {exc}", file=sys.stderr)
                    continue

            rel_path = filepath.relative_to(_SKILLS_ROOT)
            results.append({
                "name": filepath.stem,
                "path": str(rel_path).replace("\\", "/"),
                "content": content,
                "type": "yml" if filepath.suffix == ".yml" else "md",
            })

    results.sort(key=lambda d: d["name"])
    return results


def estimate_tokens(text: str) -> int:
    """Estimate token count for a text string.

    Uses tiktoken for precise counting when available, otherwise falls back
    to a simple len/4 approximation.
    """
    try:
        import tiktoken

        enc = tiktoken.encoding_for_model("gpt-4")
        return len(enc.encode(text))
    except ImportError:
        return len(text) // 4


def truncate_to_budget(
    skills: list[dict],
    domains: list[dict],
    budget: int = 8000,
) -> tuple[list[dict], list[dict]]:
    """Truncate skills and domains to fit within a token budget.

    Strategy (applied in order until under budget):
    1. Strip gotchas from each skill.
    2. Truncate workflow_steps to first 3 per skill.

    Args:
        skills: Mutable list of skill dicts (will be modified in place).
        domains: List of domain dicts (passed through unchanged).
        budget: Target token count.

    Returns:
        Tuple of (skills, domains) — potentially truncated.
    """
    def _total_tokens() -> int:
        blob = "\n".join(
            str(s) for s in skills
        ) + "\n".join(
            str(d) for d in domains
        )
        return estimate_tokens(blob)

    # Pass 1: strip gotchas
    if _total_tokens() > budget:
        for skill in skills:
            skill["gotchas"] = []

    # Pass 2: truncate workflow_steps to first 3
    if _total_tokens() > budget:
        for skill in skills:
            skill["workflow_steps"] = skill.get("workflow_steps", [])[:3]

    return skills, domains
