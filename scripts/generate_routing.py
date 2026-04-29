#!/usr/bin/env python3
"""Generate the skill routing table in CLAUDE.md from skills/*/metadata.yml.

Reads each skill's metadata.yml, extracts triggers[] and description fields,
and regenerates the content between <!-- BEGIN AUTO-ROUTING --> and
<!-- END AUTO-ROUTING --> sentinels in CLAUDE.md.

Usage:
  py scripts/generate_routing.py [--claude-md PATH] [--skills-dir PATH] [--dry-run]

Idempotent: running twice produces byte-identical output.
Graceful: skills without metadata.yml are silently skipped.
Safe: aborts if sentinels are absent rather than overwriting the whole file.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BEGIN_SENTINEL = "<!-- BEGIN AUTO-ROUTING -->"
END_SENTINEL = "<!-- END AUTO-ROUTING -->"

# Maps pack field value → routing section header
PACK_TO_SECTION: dict[str, str] = {
    "core": "Build Pipeline (sequential: think → plan → build → review → verify → ship)",
    "quality": "Quality & Learning",
    "meta": "Session Management",
    "career": "Analysis & Career",
    "analyze": "Analysis & Career",
}

# Skills that belong to named sections regardless of pack value
SKILL_SECTION_OVERRIDES: dict[str, str] = {
    "scan": "Security Pack",
    "mitigate": "Security Pack",
    "comply": "Security Pack",
    "netcompat": "Security Pack",
    "security-dashboard": "Security Pack",
    "dast": "Security Pack",
    "binary-scan": "Security Pack",
    "design": "Visual & Design",
    "polish": "Visual & Design",
    "saas-build": "Domain Builders",
    "game-dev": "Domain Builders",
    "mcp-build": "Domain Builders",
    "dashboard-dev": "Domain Builders",
    "client-work": "Domain Builders",
    "domain-re": "Domain Builders",
}

# Preferred section order in the output
SECTION_ORDER = [
    "Build Pipeline (sequential: think → plan → build → review → verify → ship)",
    "Quality & Learning",
    "Security Pack",
    "Visual & Design",
    "Domain Builders",
    "Analysis & Career",
    "Session Management",
]


def _parse_simple_yaml_field(text: str, field: str) -> str:
    """Extract a scalar string field from a minimal YAML file."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{field}:"):
            value = stripped[len(f"{field}:"):].strip()
            return value.strip('"\'')
    return ""


def _parse_triggers(text: str) -> list[str]:
    """Extract the triggers list from a metadata.yml text."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("triggers:"):
            raw = stripped[len("triggers:"):].strip()
            if raw.startswith("[") and raw.endswith("]"):
                inner = raw[1:-1]
                if not inner.strip():
                    return []
                parts = [p.strip().strip('"\'') for p in inner.split(",") if p.strip()]
                return parts
    return []


def _extract_intent(description: str) -> str:
    """Get the first sentence of a description (before 'Trigger on')."""
    for sep in (" Trigger on ", " — Trigger", ". Trigger"):
        idx = description.find(sep)
        if idx > 0:
            return description[:idx].strip()
    # Fallback: truncate at first period
    idx = description.find(".")
    if idx > 0:
        return description[:idx].strip()
    return description[:80].strip()


def _parse_description_triggers(description: str) -> list[str]:
    """Fallback: extract trigger keywords from description text.

    Looks for patterns like `keyword:` or backtick-quoted trigger phrases.
    """
    triggers: list[str] = []
    for match in re.finditer(r"`([^`]+)`", description):
        candidate = match.group(1)
        if (
            "Trigger" not in candidate
            and len(candidate) < 40
            and any(c in candidate for c in (":", "/"))
        ):
            triggers.append(candidate)
    return triggers


def collect_skills(skills_dir: Path) -> list[dict]:
    """Return a list of skill dicts for all skills with metadata.yml."""
    skills = []
    for metadata_path in sorted(skills_dir.glob("*/metadata.yml")):
        skill_name = metadata_path.parent.name
        try:
            text = metadata_path.read_text(encoding="utf-8")
        except OSError:
            continue

        name = _parse_simple_yaml_field(text, "name") or skill_name
        description = _parse_simple_yaml_field(text, "description")
        pack = _parse_simple_yaml_field(text, "pack")
        triggers = _parse_triggers(text)

        if not triggers:
            triggers = _parse_description_triggers(description)

        if not triggers:
            continue  # nothing to emit for this skill

        section = SKILL_SECTION_OVERRIDES.get(name) or PACK_TO_SECTION.get(pack, "")
        if not section:
            continue

        intent = _extract_intent(description) or name
        skills.append(
            {
                "name": name,
                "section": section,
                "intent": intent,
                "triggers": triggers,
            }
        )
    return skills


def generate_routing_block(skills: list[dict]) -> str:
    """Build the routing table markdown to insert between sentinels."""
    by_section: dict[str, list[dict]] = {}
    for skill in skills:
        by_section.setdefault(skill["section"], []).append(skill)

    lines: list[str] = []
    for section in SECTION_ORDER:
        section_skills = by_section.get(section)
        if not section_skills:
            continue
        lines.append(f"### {section}")
        lines.append("| Intent | Skill | Triggers |")
        lines.append("|--------|-------|----------|")
        for s in section_skills:
            trigger_str = ", ".join(s["triggers"])
            lines.append(f"| {s['intent']} | `dream-studio:{s['name']}` | {trigger_str} |")
        lines.append("")  # blank line between sections

    # Remove trailing blank line
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def update_claude_md(claude_md_path: Path, skills_dir: Path, dry_run: bool = False) -> bool:
    """Replace content between sentinels in CLAUDE.md. Returns True if changed."""
    if not claude_md_path.is_file():
        print(f"Error: {claude_md_path} not found", file=sys.stderr)
        return False

    text = claude_md_path.read_text(encoding="utf-8")
    begin_idx = text.find(BEGIN_SENTINEL)
    end_idx = text.find(END_SENTINEL)

    if begin_idx < 0 or end_idx < 0:
        print(
            f"Error: sentinels not found in {claude_md_path}. "
            f"Add '{BEGIN_SENTINEL}' and '{END_SENTINEL}' markers first.",
            file=sys.stderr,
        )
        return False

    if end_idx <= begin_idx:
        print(f"Error: END sentinel appears before BEGIN sentinel in {claude_md_path}", file=sys.stderr)
        return False

    skills = collect_skills(skills_dir)
    new_block = generate_routing_block(skills)

    before = text[: begin_idx + len(BEGIN_SENTINEL)]
    after = text[end_idx:]
    new_text = f"{before}\n{new_block}\n{after}"

    if new_text == text:
        if not dry_run:
            print(f"[generate_routing] {claude_md_path} — no changes needed.")
        return False

    if not dry_run:
        claude_md_path.write_text(new_text, encoding="utf-8")
        changed_skills = len(skills)
        print(f"[generate_routing] Updated {claude_md_path} — {changed_skills} skills registered.")
    else:
        print("[generate_routing] Dry-run: would update routing table.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="generate_routing",
        description="Regenerate CLAUDE.md skill routing table from skills/*/metadata.yml",
    )
    parser.add_argument(
        "--claude-md",
        default=str(Path(__file__).resolve().parents[1] / "CLAUDE.md"),
        help="Path to CLAUDE.md (default: repo root)",
    )
    parser.add_argument(
        "--skills-dir",
        default=str(Path(__file__).resolve().parents[1] / "skills"),
        help="Path to skills/ directory (default: repo root/skills)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing",
    )
    args = parser.parse_args()

    update_claude_md(
        claude_md_path=Path(args.claude_md),
        skills_dir=Path(args.skills_dir),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
