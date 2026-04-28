#!/usr/bin/env python3
"""
Apply architecture enhancement to all skills.

Creates metadata.yml, gotchas.yml, config.yml for each skill.
Extracts data from SKILL.md frontmatter and content.
"""

import re
from pathlib import Path

SKILLS_DIR = Path(__file__).parent
SKIP_DIRS = {"core", "domains", "templates", ".sessions"}


def parse_simple_yaml(yaml_text):
    """Simple YAML parser for frontmatter (key: value pairs only)."""
    result = {}
    for line in yaml_text.strip().split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            result[key.strip()] = value.strip()
    return result


def extract_frontmatter(content):
    """Extract YAML frontmatter from SKILL.md."""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if match:
        try:
            return parse_simple_yaml(match.group(1))
        except:
            return {}
    return {}


def has_imports_section(content):
    """Check if SKILL.md has ## Imports section and extract modules."""
    imports_match = re.search(r'^## Imports\s*\n(.*?)(?=\n##|\Z)', content, re.MULTILINE | re.DOTALL)
    if not imports_match:
        return []

    imports_text = imports_match.group(1)
    modules = []

    # Look for core/module.md references
    module_refs = re.findall(r'core/([a-z-]+)\.md', imports_text)
    modules.extend(module_refs)

    return list(set(modules))  # Deduplicate


def format_yaml_list(items):
    """Format a list for YAML output."""
    if not items:
        return "[]"
    return "[" + ", ".join(items) + "]"


def create_metadata_yml(skill_dir, frontmatter, core_modules):
    """Create metadata.yml content for a skill."""
    name = frontmatter.get('name', skill_dir.name)
    description = frontmatter.get('description', 'No description').strip('"')
    pack = frontmatter.get('pack', 'core')

    # Determine tags from name and description
    tags = []
    if 'security' in name or 'security' in description.lower():
        tags.append('security')
    if 'career' in name:
        tags.append('career')
    if any(word in description.lower() for word in ['analyze', 'analysis', 'review']):
        tags.append('analysis')
    if 'build' in name or 'implement' in description.lower():
        tags.append('implementation')
    if 'debug' in name or 'fix' in description.lower():
        tags.append('debugging')
    if not tags:
        tags = ['workflow']

    # Determine tools_required based on core_modules
    tools_required = []
    if 'git' in core_modules:
        tools_required.extend(['git', 'gh'])

    # Format core_modules list
    core_modules_str = format_yaml_list(core_modules)
    tools_required_str = format_yaml_list(tools_required)
    tags_str = format_yaml_list(tags)

    yaml_content = f"""# Required fields
name: {name}
version: 1.0.0
pack: {pack}
created_at: 2026-04-28
updated_at: 2026-04-28

# Evolution tracking
origin: imported
parent_skills: []
generation: 0
created_by: human

# Quality & Health
status: tested
health: active
tested_with_models: [sonnet]
tested_with_hosts: [claude-code]

# Performance metrics
quality_metrics:
  times_used: 0
  success_rate: 0.0
  avg_token_usage: 0
  avg_execution_time_seconds: 0
  last_success: null
  last_failure: null

# Failure patterns
common_failures: []

# Dependencies
dependencies:
  core_modules: {core_modules_str}
  tools_required: {tools_required_str}
  env_vars_required: []
  files_required: []
  calls_skills: []

# Compatibility
compatibility:
  min_context_window: 100000
  works_best_with: sonnet
  works_with: [haiku, sonnet, opus]
  platforms: [windows, macos, linux]

# Discovery
tags: {tags_str}
category: workflow
triggers: []
description: "{description}"
"""
    return yaml_content


def create_gotchas_yml():
    """Create empty gotchas.yml content."""
    return """version: 1.0

# Things to AVOID
avoid: []

# Best PRACTICES
best_practices: []

# Edge CASES handled
edge_cases: []

# Known LIMITATIONS
limitations: []

# DEPRECATIONS
deprecated: []
"""


def create_config_yml(name):
    """Create config.yml content with sensible defaults."""
    # Adjust for specific skills
    allow_parallel = 'true' if name in ['build', 'secure', 'analyze', 'review'] else 'false'
    max_tokens = 150000 if name in ['build', 'secure', 'analyze', 'review'] else 100000

    return f"""# Thresholds
thresholds:
  max_tasks_before_checkpoint: 3
  checkpoint_interval_minutes: 30

# Model defaults
models:
  default: sonnet
  fast_mode: haiku

# Behavior flags
behavior:
  allow_parallel_execution: {allow_parallel}
  strict_mode: false

# Performance budgets
budgets:
  max_tokens: {max_tokens}
  max_time_seconds: 600
  max_context_percent: 80
"""


def process_skill(skill_dir):
    """Process a single skill directory."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        print(f"WARNING: Skipping {skill_dir.name}: no SKILL.md")
        return False

    # Skip if metadata already exists
    metadata_file = skill_dir / "metadata.yml"
    if metadata_file.exists():
        print(f"SKIP: {skill_dir.name}: metadata.yml already exists")
        return False

    print(f"Processing {skill_dir.name}...")

    # Read SKILL.md
    with open(skill_md, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract frontmatter and imports
    frontmatter = extract_frontmatter(content)
    core_modules = has_imports_section(content)

    # Create files
    name = frontmatter.get('name', skill_dir.name)
    metadata_content = create_metadata_yml(skill_dir, frontmatter, core_modules)
    gotchas_content = create_gotchas_yml()
    config_content = create_config_yml(name)

    # Write metadata.yml
    with open(skill_dir / "metadata.yml", 'w', encoding='utf-8') as f:
        f.write(metadata_content)

    # Write gotchas.yml
    with open(skill_dir / "gotchas.yml", 'w', encoding='utf-8') as f:
        f.write(gotchas_content)

    # Write config.yml
    with open(skill_dir / "config.yml", 'w', encoding='utf-8') as f:
        f.write(config_content)

    print(f"DONE: {skill_dir.name}: metadata.yml, gotchas.yml, config.yml created")
    return True


def main():
    """Process all skills."""
    print("Applying architecture enhancement to all skills...\n")

    processed = 0
    skipped = 0

    for item in sorted(SKILLS_DIR.iterdir()):
        if not item.is_dir() or item.name in SKIP_DIRS:
            continue

        if process_skill(item):
            processed += 1
        else:
            skipped += 1

    print(f"\n{'='*60}")
    print(f"Processed: {processed} skills")
    print(f"Skipped: {skipped} skills")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
