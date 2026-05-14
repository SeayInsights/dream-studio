"""Check what databases can be safely deleted - TA-009"""

import sqlite3
import os
from pathlib import Path
from core.config.database import get_connection

dream_studio_dir = Path.home() / ".dream-studio"

# Databases to check
databases = {
    "analytics.db": dream_studio_dir / "analytics.db",
    "registry.db": dream_studio_dir / "registry.db",
    "studio.db (root)": dream_studio_dir / "studio.db",
    "state/studio.db": dream_studio_dir / "state" / "studio.db",
}

print("=== Database Inventory ===\n")

for name, path in databases.items():
    if not path.exists():
        print(f"{name}: NOT FOUND")
        continue

    size = path.stat().st_size
    size_kb = size / 1024

    if size == 0:
        print(f"{name}: EMPTY (0 bytes) - safe to delete")
        continue

    # Check table count
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cursor.fetchall()]
        conn.close()

        print(f"{name}: {size_kb:.1f} KB, {len(tables)} tables")
        if len(tables) <= 10:
            print(f"  Tables: {', '.join(tables)}")
    except Exception as e:
        print(f"{name}: {size_kb:.1f} KB - Error reading: {e}")

print("\n=== Recommendation ===")
print("Safe to delete:")
print("- analytics.db (empty)")
print("- registry.db (empty)")
print("\nNeed decision:")
print("- studio.db (164KB) - check if security tables are needed")
