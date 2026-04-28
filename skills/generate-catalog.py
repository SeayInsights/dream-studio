#!/usr/bin/env python3
"""
Dream-Studio Skill Catalog Generator

Reads all */metadata.yml files and generates dream-studio-catalog.md with:
- Skill listing by pack
- Quality metrics
- Dependency graph
- Health dashboard
- Performance insights
"""

import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Base directory
SKILLS_DIR = Path(__file__).parent
CATALOG_FILE = SKILLS_DIR / "dream-studio-catalog.md"

# Directories to skip
SKIP_DIRS = {"core", "domains", "templates", ".sessions"}


def parse_yaml_value(value_str):
    """Parse a YAML value (handles strings, numbers, lists, bools, null)."""
    value_str = value_str.strip()

    # Handle null
    if value_str in ('null', '~', ''):
        return None

    # Handle booleans
    if value_str in ('true', 'True', 'yes', 'Yes'):
        return True
    if value_str in ('false', 'False', 'no', 'No'):
        return False

    # Handle lists [item1, item2, ...]
    if value_str.startswith('[') and value_str.endswith(']'):
        items = value_str[1:-1].split(',')
        return [item.strip() for item in items if item.strip()]

    # Handle numbers
    try:
        if '.' in value_str:
            return float(value_str)
        return int(value_str)
    except ValueError:
        pass

    # Handle strings (remove quotes)
    if value_str.startswith('"') and value_str.endswith('"'):
        return value_str[1:-1]
    if value_str.startswith("'") and value_str.endswith("'"):
        return value_str[1:-1]

    return value_str


def parse_yaml_simple(content):
    """Simple YAML parser for metadata files."""
    result = {}
    current_key = None
    indent_level = 0

    for line in content.split('\n'):
        # Skip comments and empty lines
        if line.strip().startswith('#') or not line.strip():
            continue

        # Count indentation
        stripped = line.lstrip()
        current_indent = len(line) - len(stripped)

        # Key-value pair
        if ':' in stripped:
            key, value = stripped.split(':', 1)
            key = key.strip()
            value = value.strip()

            if current_indent == 0:
                # Top-level key
                if value:
                    result[key] = parse_yaml_value(value)
                else:
                    result[key] = {}
                    current_key = key
            elif current_key:
                # Nested key
                if value:
                    if not isinstance(result[current_key], dict):
                        result[current_key] = {}
                    result[current_key][key] = parse_yaml_value(value)

    return result


def load_all_metadata():
    """Load all metadata.yml files from skill directories."""
    skills = []

    for item in SKILLS_DIR.iterdir():
        if not item.is_dir() or item.name in SKIP_DIRS:
            continue

        metadata_file = item / "metadata.yml"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    metadata = parse_yaml_simple(content)
                    metadata['_dir'] = item.name
                    skills.append(metadata)
            except Exception as e:
                print(f"Warning: Failed to load {metadata_file}: {e}")

    return skills


def generate_skills_by_pack(skills):
    """Generate Skills by Pack section."""
    packs = defaultdict(list)
    for skill in skills:
        pack = skill.get('pack', 'unknown')
        packs[pack].append(skill)

    # Sort packs and skills
    output = ["## Skills by Pack\n"]

    for pack in sorted(packs.keys()):
        pack_skills = sorted(packs[pack], key=lambda s: s.get('name', ''))
        output.append(f"### {pack.title()} Pack ({len(pack_skills)} skills)\n")

        for skill in pack_skills:
            name = skill.get('name', 'unknown')
            version = skill.get('version', '0.0.0')
            status = skill.get('status', 'unknown')
            health = skill.get('health', 'unknown')
            description = skill.get('description', 'No description')

            metrics = skill.get('quality_metrics', {})
            success_rate = metrics.get('success_rate', 0.0) * 100
            times_used = metrics.get('times_used', 0)
            avg_tokens = metrics.get('avg_token_usage', 0)

            health_icon = "✅" if health == "active" else "⚠️" if health == "maintenance" else "❌"

            triggers = skill.get('triggers', [])
            trigger_str = ', '.join(triggers[:3]) if triggers else 'N/A'

            output.append(f"- **{name}** (v{version}) — {status}, {health} {health_icon}\n")
            output.append(f"  {description}\n")
            if times_used > 0:
                output.append(f"  Success: {success_rate:.0f}% ({times_used} uses) | Tokens: {avg_tokens:,} avg\n")
            if triggers:
                output.append(f"  Triggers: {trigger_str}\n")
            output.append("\n")

    return ''.join(output)


def generate_quality_metrics(skills):
    """Generate Quality Metrics section."""
    output = ["## Quality Metrics\n"]

    # Filter skills with usage data
    used_skills = [s for s in skills if s.get('quality_metrics', {}).get('times_used', 0) > 0]

    if not used_skills:
        output.append("*No usage data yet*\n\n")
        return ''.join(output)

    # Sort by success rate
    by_success = sorted(used_skills, key=lambda s: s.get('quality_metrics', {}).get('success_rate', 0), reverse=True)[:10]
    output.append("### Top 10 by Success Rate\n")
    for i, skill in enumerate(by_success, 1):
        name = skill.get('name', 'unknown')
        metrics = skill.get('quality_metrics', {})
        success = metrics.get('success_rate', 0.0) * 100
        uses = metrics.get('times_used', 0)
        output.append(f"{i}. **{name}** — {success:.0f}% ({uses} uses) {'✅' if success >= 90 else '⚠️'}\n")
    output.append("\n")

    # Sort by token usage
    by_tokens = sorted(used_skills, key=lambda s: s.get('quality_metrics', {}).get('avg_token_usage', 0), reverse=True)[:10]
    output.append("### Top 10 by Token Usage (avg)\n")
    for i, skill in enumerate(by_tokens, 1):
        name = skill.get('name', 'unknown')
        tokens = skill.get('quality_metrics', {}).get('avg_token_usage', 0)
        weight = "heavy" if tokens > 20000 else "medium" if tokens > 10000 else "light"
        output.append(f"{i}. **{name}** — {tokens:,} tokens ({weight})\n")
    output.append("\n")

    # Sort by times used
    by_usage = sorted(used_skills, key=lambda s: s.get('quality_metrics', {}).get('times_used', 0), reverse=True)[:10]
    output.append("### Top 10 by Usage Count\n")
    for i, skill in enumerate(by_usage, 1):
        name = skill.get('name', 'unknown')
        uses = skill.get('quality_metrics', {}).get('times_used', 0)
        output.append(f"{i}. **{name}** — {uses} uses\n")
    output.append("\n")

    return ''.join(output)


def generate_dependency_graph(skills):
    """Generate Dependency Graph section."""
    output = ["## Dependency Graph\n"]

    # Count core module usage
    module_usage = defaultdict(list)
    for skill in skills:
        deps = skill.get('dependencies', {})
        modules = deps.get('core_modules', [])
        for module in modules:
            module_usage[module].append(skill.get('name', 'unknown'))

    if module_usage:
        output.append("### Core Module Usage\n")
        for module in sorted(module_usage.keys()):
            users = module_usage[module]
            output.append(f"- **core/{module}.md** → {len(users)} skills: {', '.join(sorted(users[:5]))}")
            if len(users) > 5:
                output.append(f", +{len(users) - 5} more")
            output.append("\n")
        output.append("\n")
    else:
        output.append("*No core module dependencies tracked yet*\n\n")

    # Count tool dependencies
    tool_usage = defaultdict(list)
    for skill in skills:
        deps = skill.get('dependencies', {})
        tools = deps.get('tools_required', [])
        for tool in tools:
            tool_usage[tool].append(skill.get('name', 'unknown'))

    if tool_usage:
        output.append("### Tool Dependencies\n")
        for tool in sorted(tool_usage.keys()):
            users = tool_usage[tool]
            output.append(f"- **{tool}** → {len(users)} skills\n")
        output.append("\n")

    return ''.join(output)


def generate_health_dashboard(skills):
    """Generate Health Dashboard section."""
    output = ["## Health Dashboard\n"]

    # Count by health status
    health_counts = defaultdict(int)
    status_counts = defaultdict(int)

    for skill in skills:
        health = skill.get('health', 'unknown')
        status = skill.get('status', 'unknown')
        health_counts[health] += 1
        status_counts[status] += 1

    output.append("### By Health Status\n")
    for health in ['active', 'maintenance', 'deprecated']:
        count = health_counts.get(health, 0)
        icon = "✅" if health == "active" else "⚠️" if health == "maintenance" else "❌"
        output.append(f"- {health.title()}: {count} skills {icon}\n")
    output.append("\n")

    output.append("### By Development Status\n")
    for status in ['stable', 'tested', 'experimental', 'deprecated']:
        count = status_counts.get(status, 0)
        output.append(f"- {status.title()}: {count} skills\n")
    output.append("\n")

    return ''.join(output)


def generate_catalog(skills):
    """Generate the full catalog markdown."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    output = [
        "# Dream-Studio Skill Catalog\n\n",
        f"**Generated:** {now}\n",
        f"**Total Skills:** {len(skills)}\n\n",
        "---\n\n"
    ]

    output.append(generate_skills_by_pack(skills))
    output.append("\n---\n\n")
    output.append(generate_quality_metrics(skills))
    output.append("\n---\n\n")
    output.append(generate_dependency_graph(skills))
    output.append("\n---\n\n")
    output.append(generate_health_dashboard(skills))

    return ''.join(output)


def main():
    """Main execution."""
    print("Loading metadata from all skills...")
    skills = load_all_metadata()
    print(f"Found {len(skills)} skills")

    print("Generating catalog...")
    catalog = generate_catalog(skills)

    print(f"Writing catalog to {CATALOG_FILE}...")
    with open(CATALOG_FILE, 'w', encoding='utf-8') as f:
        f.write(catalog)

    print("DONE: Catalog generated successfully!")
    print(f"File: {CATALOG_FILE}")


if __name__ == "__main__":
    main()
