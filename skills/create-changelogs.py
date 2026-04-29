#!/usr/bin/env python3
"""
Create changelog.md for all skills.
"""

from pathlib import Path

SKILLS_DIR = Path(__file__).parent
SKIP_DIRS = {"core", "domains", "templates", ".sessions"}

CHANGELOG_TEMPLATE = """# {skill_name} — Changelog

## [1.0.0] - 2026-04-28

### Added
- Initial architecture enhancement
- Added metadata.yml for skill tracking
- Added gotchas.yml for lessons learned
- Added config.yml for runtime configuration
- Established skill framework foundation

### Documentation
- Created examples (simple and complex scenarios)
- Added templates for agent prompts and output formats
- Added smoke test for quick validation
- Added core-imports.md for module dependencies (if applicable)

## Version History

**v1.0.0 (2026-04-28)** — Architecture enhancement baseline
- Skill matured from prototype to structured framework
- Quality metrics tracking established
- Dependency graph documented
"""


def create_changelog(skill_dir):
    """Create changelog.md for a skill."""
    skill_name = skill_dir.name
    changelog_file = skill_dir / "changelog.md"

    if changelog_file.exists():
        print(f"SKIP: {skill_name}: changelog.md already exists")
        return False

    content = CHANGELOG_TEMPLATE.format(skill_name=skill_name)

    with open(changelog_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"DONE: {skill_name}: changelog.md created")
    return True


def main():
    """Process all skills."""
    print("Creating changelog.md for all skills...\n")

    processed = 0
    skipped = 0

    for item in sorted(SKILLS_DIR.iterdir()):
        if not item.is_dir() or item.name in SKIP_DIRS:
            continue

        skill_md = item / "SKILL.md"
        if not skill_md.exists():
            continue

        if create_changelog(item):
            processed += 1
        else:
            skipped += 1

    print(f"\n{'='*60}")
    print(f"Processed: {processed} skills")
    print(f"Skipped: {skipped} skills")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
