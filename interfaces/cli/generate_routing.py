#!/usr/bin/env python3
"""Generate the skill routing table in CLAUDE.md from every skill's metadata.yml.

Reads each skill's metadata.yml, extracts triggers[] and description fields,
and regenerates the content between <!-- BEGIN AUTO-ROUTING --> and
<!-- END AUTO-ROUTING --> sentinels in CLAUDE.md.

Usage:
  py interfaces/cli/generate_routing.py [--claude-md PATH] [--skills-dir PATH] [--dry-run]

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
    "analyze": "Analysis",
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
    "power-platform": "Domain Builders",
    "domain-re": "Domain Builders",
}

# Preferred section order in the output
SECTION_ORDER = [
    "Build Pipeline (sequential: think → plan → build → review → verify → ship)",
    "Quality & Learning",
    "Security Pack",
    "Visual & Design",
    "Domain Builders",
    "Analysis",
    "Session Management",
]


def _parse_simple_yaml_field(text: str, field: str) -> str:
    """Extract a scalar string field from a minimal YAML file."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{field}:"):
            value = stripped[len(f"{field}:") :].strip()
            return value.strip("\"'")
    return ""


def _parse_triggers(text: str) -> list[str]:
    """Extract the triggers list from a metadata.yml text.

    BOTH OF YAML'S LIST SPELLINGS. This read only the inline flow form
    (``triggers: [a, b]``) and returned [] for the block form::

        triggers:
          - "intake:"
          - "sow:"

    which is what 47 of the 65 modes use. A skill with no triggers is dropped from the
    routing table by the caller, so the table that makes a skill discoverable listed 19
    of 66 -- and the drop is a bare `continue`, so nothing said which or why.

    Parsed with PyYAML rather than more line-reading. The hand-rolled reader is what
    produced a parser that knew one spelling; the library knows the language. A document
    that will not parse falls back to the old scan, because a malformed metadata.yml is
    that skill's defect and should not take the whole table down with it.
    """
    try:
        import yaml

        loaded = yaml.safe_load(text)
    except Exception:
        loaded = None

    if isinstance(loaded, dict):
        raw = loaded.get("triggers")
        if isinstance(raw, list):
            out = []
            for item in raw:
                if isinstance(item, str) and item.strip():
                    out.append(item.strip())
                elif isinstance(item, dict) and len(item) == 1:
                    # `- intake:` unquoted parses as {intake: None}. That is a defect in
                    # the metadata (the colon is part of the trigger), reported by
                    # `tests/unit/test_routing_table.py`; read it here rather than
                    # dropping the skill, so one bad quote does not unroute a mode.
                    key = next(iter(item))
                    if isinstance(key, str) and key.strip():
                        out.append(f"{key.strip()}:")
            return out

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("triggers:"):
            raw_inline = stripped[len("triggers:") :].strip()
            if raw_inline.startswith("[") and raw_inline.endswith("]"):
                inner = raw_inline[1:-1]
                if not inner.strip():
                    return []
                return [p.strip().strip("\"'") for p in inner.split(",") if p.strip()]
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
    skipped: list[tuple[str, str]] = []
    # BOTH LAYOUTS. This globbed `*/metadata.yml` alone, which matched ONE file, while
    # 65 modes live a level deeper at `<pack>/modes/<mode>/metadata.yml`. The skills tree
    # moved to packs-and-modes and the glob never followed, so the routing table that
    # makes a skill discoverable listed 1 of 66 -- and the module's own "graceful: skills
    # without metadata.yml are silently skipped" is why nobody saw it: 65 silent skips
    # and a success message reading "1 skills registered".
    paths = sorted({*skills_dir.glob("*/metadata.yml"), *skills_dir.glob("*/modes/*/metadata.yml")})
    for metadata_path in paths:
        # `<pack>/modes/<mode>` is named `<pack>:<mode>`, which is how an operator
        # types it and how packs.yaml refers to it. A bare mode name would collide
        # across packs (several packs have a `security` or `review` mode).
        parent = metadata_path.parent
        if parent.parent.name == "modes":
            skill_name = f"{parent.parent.parent.name}:{parent.name}"
        else:
            skill_name = parent.name
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
            # RECORDED, NOT SWALLOWED. This was a bare `continue`, and 47 modes left the
            # table through it while the run printed "1 skills registered" as a success.
            # A skip nobody can see is the same as no check at all.
            skipped.append((skill_name, "declares no triggers, so nothing can route to it"))
            continue

        # A PACK NOBODY HARDCODED IS STILL A PACK. `PACK_TO_SECTION` names four, so
        # every mode in any other pack -- the whole `domains` pack, eleven modes
        # including website, kubernetes, terraform and mobile -- fell out of the table
        # unless it happened to be listed by name in the overrides. Falling back to the
        # pack's own name routes them under an honest heading instead of dropping them,
        # and a pack added later needs no edit here to be reachable.
        section = (
            SKILL_SECTION_OVERRIDES.get(name)
            or PACK_TO_SECTION.get(pack, "")
            or (pack.replace("-", " ").title() if pack else "")
        )
        if not section:
            skipped.append((skill_name, "no pack declared, so no section to file it under"))
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
    collect_skills.skipped = skipped  # type: ignore[attr-defined]
    return skills


def generate_routing_block(skills: list[dict]) -> str:
    """Build the routing table markdown to insert between sentinels."""
    by_section: dict[str, list[dict]] = {}
    for skill in skills:
        by_section.setdefault(skill["section"], []).append(skill)

    lines: list[str] = []
    # SECTION_ORDER IS AN ORDERING, NOT A FILTER. It named seven sections and the loop
    # iterated only those, so a skill collected under any other section was dropped at
    # render time -- after being counted. The run reported "36 skills registered" and
    # wrote 28. Known sections keep their order; anything else follows, alphabetically,
    # so a new pack appears in the table without editing this list.
    ordered = [sec for sec in SECTION_ORDER if sec in by_section]
    ordered += sorted(sec for sec in by_section if sec not in SECTION_ORDER)
    for section in ordered:
        section_skills = by_section.get(section)
        if not section_skills:
            continue
        lines.append(f"### {section}")
        lines.append("| Intent | Skill | Triggers |")
        lines.append("|--------|-------|----------|")
        for s in section_skills:
            trigger_str = ", ".join(s["triggers"])
            lines.append(f"| {s['intent']} | `ds-{s['name']}` | {trigger_str} |")
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
    skills = collect_skills(skills_dir)
    new_block = generate_routing_block(skills)

    # ONE SPLICE IMPLEMENTATION, NOT TWO (WO-CLAUDEMD-CLOBBER follow-up).
    #
    # This function found the markers, checked their order, and sliced -- the same contract
    # merge_claude_md implements for the installer. An independent review named the risk
    # precisely: "the contract was re-implemented in the compiler rather than shared with
    # generate_routing, leaving two splice implementations that can still drift apart."
    #
    # Drift here is not cosmetic. These two writers target the SAME files, so if one
    # tightened its refusal and the other did not, the operator's CLAUDE.md would be safe
    # from one path and clobbered by the other -- which is the defect the original work
    # order existed to fix, reintroduced through the back door.
    from integrations.compiler.claude_code import CLAUDE_MD_REFUSED, merge_claude_md

    new_text, disposition, detail = merge_claude_md(text, new_block)
    if disposition == CLAUDE_MD_REFUSED or new_text is None:
        print(f"Error: {claude_md_path} {detail}", file=sys.stderr)
        return False

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

    # A COUNT OF WHAT WORKED IS NOT A REPORT. Every earlier version printed only the
    # number registered, and each of the four ways a skill could leave the table was a
    # bare `continue` -- so "1 skills registered" read as success while 65 modes were
    # unreachable. A skill that cannot be routed to is invisible to the operator in the
    # only way that matters, so the run says which, and why, whether or not it wrote.
    dropped = getattr(collect_skills, "skipped", None) or []
    if dropped:
        print(f"[generate_routing] {len(dropped)} skill(s) are NOT in the routing table:")
        for name, reason in sorted(dropped):
            print(f"    {name}: {reason}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="generate_routing",
        description="Regenerate the CLAUDE.md skill routing table from every metadata.yml",
    )
    parser.add_argument(
        "--claude-md",
        # parents[2] IS THE REPOSITORY ROOT. This read parents[1] and resolved to
        # interfaces/CLAUDE.md -- correct while the file lived in scripts/, and wrong
        # from the day it moved, so the tool could not run with its own defaults.
        default=str(Path(__file__).resolve().parents[2] / "CLAUDE.md"),
        help="Path to CLAUDE.md (default: repo root)",
    )
    parser.add_argument(
        "--skills-dir",
        default=str(Path(__file__).resolve().parents[2] / "canonical" / "skills"),
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
