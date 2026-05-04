#!/usr/bin/env python3
"""Check database schema version."""
import sqlite3
from pathlib import Path

db_path = Path.home() / ".dream-studio" / "state" / "studio.db"

if not db_path.exists():
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.execute("SELECT version, applied_at FROM _schema_version ORDER BY version DESC LIMIT 5")
rows = cursor.fetchall()
conn.close()

print("Applied schema versions:")
for version, applied_at in rows:
    print(f"  v{version} - {applied_at}")

if rows:
    print(f"\nCurrent schema version: {rows[0][0]}")
