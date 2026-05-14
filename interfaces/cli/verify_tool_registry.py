#!/usr/bin/env python3
"""Quick verification script to show seeded tool registry contents."""

import json
import sqlite3
from pathlib import Path
from core.config.database import get_connection

STUDIO_DB = Path.home() / ".dream-studio" / "state" / "studio.db"

conn = get_connection()
cursor = conn.cursor()

print("=== TOOL REGISTRY SUMMARY ===\n")
cursor.execute("SELECT category, COUNT(*) FROM tool_registry GROUP BY category ORDER BY category")
cats = cursor.fetchall()
for cat, count in cats:
    print(f"{cat}: {count}")

print(f"\nTotal: {sum(c[1] for c in cats)} tools\n")

print("=== SAMPLE TOOLS BY CATEGORY ===\n")
for cat in ["mcp", "python_package", "api", "saas"]:
    cursor.execute("SELECT name, description FROM tool_registry WHERE category = ? LIMIT 2", (cat,))
    print(f"{cat.upper()}:")
    for name, desc in cursor.fetchall():
        print(f"  - {name}: {desc[:60]}...")
    print()

conn.close()
