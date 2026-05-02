#!/usr/bin/env python3
"""
Validate SKILL.md files against dream-studio standards.

Validation checks:
1. Line count limits (main <300, modes <150)
2. YAML frontmatter syntax
3. Banned scaffolding phrases
4. Reference link integrity
"""

import sys
import re
from pathlib import Path
from typing import List, Tuple, Optional
import yaml


class ValidationResult:
    def __init__(self, check_name: str):
        self.check_name = check_name
        self.errors: List[Tuple[str, str]] = []
        self.warnings: List[Tuple[str, str]] = []

    def add_error(self, file_path: str, message: str):
        self.errors.append((file_path, message))

    def add_warning(self, file_path: str, message: str):
        self.warnings.append((file_path, message))

    def has_failures(self) -> bool:
        return len(self.errors) > 0

    def print_results(self):
        if not self.errors and not self.warnings:
            print(f"[PASS] {self.check_name}: All checks passed")
            return

        if self.errors:
            print(f"[FAIL] {self.check_name}: {len(self.errors)} error(s)")
            for file_path, message in self.errors:
                print(f"   ERROR: {file_path}")
                print(f"          {message}")

        if self.warnings:
            print(f"[WARN] {self.check_name}: {len(self.warnings)} warning(s)")
            for file_path, message in self.warnings:
                print(f"   WARN:  {file_path}")
                print(f"          {message}")


def check_line_counts(skill_files: List[Path]) -> ValidationResult:
    """Check line count limits: main SKILL.md <300, mode SKILL.md <150"""
    result = ValidationResult("Line Count Limits")

    for skill_file in skill_files:
        with open(skill_file, 'r', encoding='utf-8') as f:
            line_count = sum(1 for _ in f)

        # Determine if this is a main or mode SKILL.md
        is_mode = '/modes/' in skill_file.as_posix()
        limit = 150 if is_mode else 300
        file_type = "mode" if is_mode else "main"

        if line_count > limit:
            result.add_error(
                str(skill_file),
                f"{file_type} SKILL.md has {line_count} lines (limit: {limit})"
            )

    return result


def check_yaml_frontmatter(skill_files: List[Path]) -> ValidationResult:
    """Check that YAML frontmatter blocks are valid"""
    result = ValidationResult("YAML Frontmatter Validation")

    # Pattern to match YAML frontmatter blocks
    frontmatter_pattern = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.MULTILINE | re.DOTALL)

    for skill_file in skill_files:
        with open(skill_file, 'r', encoding='utf-8') as f:
            content = f.read()

        match = frontmatter_pattern.match(content)
        if match:
            yaml_content = match.group(1)
            try:
                yaml.safe_load(yaml_content)
            except yaml.YAMLError as e:
                result.add_error(
                    str(skill_file),
                    f"Invalid YAML frontmatter: {str(e)}"
                )

    return result


def check_banned_phrases(skill_files: List[Path]) -> ValidationResult:
    """Check for scaffolding phrases that should be removed"""
    result = ValidationResult("Banned Phrases Check")

    banned_phrases = [
        "this section",
        "refer to",
        "following explains",
        "explains how",
        "you should consult",
        "when you encounter",
        "this document",
        "the below",
        "as shown below",
        "see below"
    ]

    for skill_file in skill_files:
        with open(skill_file, 'r', encoding='utf-8') as f:
            content = f.read().lower()

        found_phrases = []
        for phrase in banned_phrases:
            if phrase in content:
                # Count occurrences
                count = content.count(phrase)
                found_phrases.append(f"'{phrase}' ({count}x)")

        if found_phrases:
            result.add_warning(
                str(skill_file),
                f"Found scaffolding phrases: {', '.join(found_phrases)}"
            )

    return result


def check_reference_links(skill_files: List[Path]) -> ValidationResult:
    """Check that all reference links have corresponding anchors"""
    result = ValidationResult("Reference Link Validation")

    # Pattern for markdown links: [text](#anchor)
    link_pattern = re.compile(r'\[([^\]]+)\]\(#([^\)]+)\)')
    # Pattern for explicit anchors: {#anchor}
    explicit_anchor_pattern = re.compile(r'\{#([^\}]+)\}')
    # Pattern for heading anchors (auto-generated from headings)
    heading_pattern = re.compile(r'^#+\s+(.+)$', re.MULTILINE)

    for skill_file in skill_files:
        with open(skill_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find all reference links
        links = link_pattern.findall(content)
        link_anchors = {anchor for _, anchor in links}

        if not link_anchors:
            continue  # No reference links in this file

        # Find all explicit anchors
        explicit_anchors = set(explicit_anchor_pattern.findall(content))

        # Find all heading-based anchors (convert heading text to anchor format)
        headings = heading_pattern.findall(content)
        heading_anchors = set()
        for heading in headings:
            # Convert heading to anchor format (lowercase, replace spaces with hyphens)
            anchor = heading.lower().strip()
            anchor = re.sub(r'[^\w\s-]', '', anchor)
            anchor = re.sub(r'[\s]+', '-', anchor)
            heading_anchors.add(anchor)

        # All valid anchors
        all_anchors = explicit_anchors | heading_anchors

        # Find broken links
        broken_links = link_anchors - all_anchors
        if broken_links:
            result.add_warning(
                str(skill_file),
                f"Broken reference links: {', '.join(sorted(broken_links))}"
            )

    return result


def find_skill_files(root_dir: Path, changed_files: Optional[List[str]] = None) -> List[Path]:
    """
    Find SKILL.md files to validate.
    If changed_files is provided, only return those files.
    Otherwise, find all SKILL.md files in skills/
    """
    if changed_files:
        # Filter to only SKILL.md files in skills/
        skill_files = [
            Path(f) for f in changed_files
            if f.startswith('skills/') and f.endswith('SKILL.md')
        ]
    else:
        # Find all SKILL.md files, excluding .planning and .sessions
        skill_files = []
        for skill_file in root_dir.glob('skills/**/SKILL.md'):
            if '.planning' not in skill_file.parts and '.sessions' not in skill_file.parts:
                skill_files.append(skill_file)

    return skill_files


def main():
    # Determine root directory
    root_dir = Path(__file__).parent.parent.parent

    # Get changed files if running in CI
    changed_files = None
    if len(sys.argv) > 1:
        changed_files = sys.argv[1:]

    # Find SKILL.md files to validate
    skill_files = find_skill_files(root_dir, changed_files)

    if not skill_files:
        print("No SKILL.md files to validate")
        sys.exit(0)

    print(f"Validating {len(skill_files)} SKILL.md file(s)...\n")

    # Run all validation checks
    results = [
        check_line_counts(skill_files),
        check_yaml_frontmatter(skill_files),
        check_banned_phrases(skill_files),
        check_reference_links(skill_files)
    ]

    # Print results
    for result in results:
        result.print_results()
        print()

    # Exit with error if any check failed
    if any(result.has_failures() for result in results):
        print("[FAIL] Validation failed")
        sys.exit(1)
    else:
        print("[PASS] All validations passed")
        sys.exit(0)


if __name__ == '__main__':
    main()
