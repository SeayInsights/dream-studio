#!/usr/bin/env python3
"""
Seed Tool Registry
Created: 2026-05-05
Purpose: Load curated tools from YAML into tool_registry table

Usage:
    python scripts/seed_tool_registry.py

Database:
    ~/.dream-studio/state/studio.db
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from core.config.database import get_connection, transaction

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)


# ============================================================================
# CONSTANTS
# ============================================================================

STUDIO_DB = Path.home() / ".dream-studio" / "state" / "studio.db"
SEED_FILE = Path(__file__).parent.parent / "analytics" / "data" / "tool_registry_seed.yaml"

CATEGORIES = {
    "mcp": "MCP Server (Model Context Protocol)",
    "python_package": "Python Package (PyPI)",
    "api": "External API Service",
    "saas": "SaaS Platform",
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def slugify(text: str) -> str:
    """Convert text to slug format."""
    return text.lower().replace(" ", "-").replace("_", "-")


def generate_tool_id(category: str, name: str) -> str:
    """Generate unique tool_id: category:slug."""
    return f"{category}:{slugify(name)}"


def load_seed_data(yaml_path: Path) -> list[dict[str, Any]]:
    """Load tool definitions from YAML file."""
    if not yaml_path.exists():
        print(f"ERROR: Seed file not found: {yaml_path}")
        sys.exit(1)

    with open(yaml_path, "r", encoding="utf-8") as f:
        tools = yaml.safe_load(f)

    if not tools:
        print("ERROR: No tools found in YAML file")
        sys.exit(1)

    return tools


def validate_tool(tool: dict[str, Any]) -> bool:
    """Validate required fields in tool definition."""
    required = ["name", "category", "description", "source_url", "install_command", "tags"]
    for field in required:
        if field not in tool:
            print(f"WARNING: Tool missing required field '{field}': {tool.get('name', 'unknown')}")
            return False

    if tool["category"] not in CATEGORIES:
        print(f"WARNING: Invalid category '{tool['category']}' for tool: {tool['name']}")
        return False

    return True


def seed_tool_registry(db_path: Path, tools: list[dict[str, Any]]) -> dict[str, int]:
    """Insert tools into database. Returns stats."""
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    # Verify table exists first
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tool_registry'")
        if not cursor.fetchone():
            print("ERROR: tool_registry table does not exist. Run migration 013 first.")
            sys.exit(1)

    stats = {"total": 0, "inserted": 0, "skipped": 0}
    category_counts = {cat: 0 for cat in CATEGORIES}
    now = datetime.now().isoformat()

    with transaction() as conn:
        cursor = conn.cursor()

        for tool in tools:
            stats["total"] += 1

            # Validate
            if not validate_tool(tool):
                stats["skipped"] += 1
                continue

            # Generate tool_id
            tool_id = generate_tool_id(tool["category"], tool["name"])

            # Serialize tags to JSON
            tags_json = json.dumps(tool.get("tags", []))

            # Insert or replace
            try:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO tool_registry (
                        tool_id,
                        name,
                        category,
                        description,
                        source_url,
                        install_command,
                        tags,
                        confidence_score,
                        last_verified_at,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tool_id,
                        tool["name"],
                        tool["category"],
                        tool["description"],
                        tool["source_url"],
                        tool["install_command"],
                        tags_json,
                        tool.get("confidence_score", 0.7),
                        now,
                        now,
                    ),
                )
                stats["inserted"] += 1
                category_counts[tool["category"]] += 1

            except sqlite3.Error as e:
                print(f"ERROR inserting tool '{tool['name']}': {e}")
                stats["skipped"] += 1

    # Add category breakdown to stats
    stats["by_category"] = {cat: count for cat, count in category_counts.items() if count > 0}

    return stats


def print_summary(stats: dict[str, Any]) -> None:
    """Print seeding summary."""
    print("\n" + "=" * 60)
    print("TOOL REGISTRY SEED COMPLETE")
    print("=" * 60)
    print(f"Total tools processed: {stats['total']}")
    print(f"Successfully inserted: {stats['inserted']}")
    print(f"Skipped (validation): {stats['skipped']}")
    print()
    print("Category breakdown:")
    for category, count in stats["by_category"].items():
        print(f"  {CATEGORIES[category]}: {count}")
    print("=" * 60)


# ============================================================================
# MAIN
# ============================================================================


def main() -> None:
    """Load YAML seed file and insert tools into database."""
    print(f"Loading seed data from: {SEED_FILE}")
    tools = load_seed_data(SEED_FILE)
    print(f"Found {len(tools)} tools in seed file")

    print(f"\nSeeding database: {STUDIO_DB}")
    stats = seed_tool_registry(STUDIO_DB, tools)

    print_summary(stats)


if __name__ == "__main__":
    main()
