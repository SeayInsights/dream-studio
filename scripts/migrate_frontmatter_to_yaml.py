#!/usr/bin/env python3
"""One-time migration: extract SKILL.md frontmatter into config.yml files."""

import re
import sys
from pathlib import Path

import yaml

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)

def migrate(skill_md: Path, dry_run: bool = False) -> bool:
    text = skill_md.read_text(encoding="utf-8-sig")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return False

    frontmatter_raw = match.group(1)
    config = yaml.safe_load(frontmatter_raw)
    if not config or not isinstance(config, dict):
        return False

    config_path = skill_md.parent / "config.yml"
    body = text[match.end():]

    if dry_run:
        print(f"  Would create: {config_path}")
        print(f"  Would strip frontmatter from: {skill_md}")
        return True

    # Write config.yml
    with config_path.open("w", encoding="utf-8", newline="\n") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # Strip frontmatter from SKILL.md
    with skill_md.open("w", encoding="utf-8", newline="\n") as f:
        f.write(body)

    return True

def main():
    dry_run = "--dry-run" in sys.argv
    root = Path(__file__).resolve().parents[1] / "skills"

    skill_files = sorted(root.rglob("SKILL.md"))
    print(f"Found {len(skill_files)} SKILL.md files")

    migrated = 0
    for sf in skill_files:
        if migrate(sf, dry_run=dry_run):
            migrated += 1
            print(f"  {'[DRY RUN] ' if dry_run else ''}Migrated: {sf.relative_to(root.parent)}")
        else:
            print(f"  Skipped (no frontmatter): {sf.relative_to(root.parent)}")

    print(f"\n{'Would migrate' if dry_run else 'Migrated'} {migrated}/{len(skill_files)} files")

if __name__ == "__main__":
    main()
