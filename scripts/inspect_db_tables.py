#!/usr/bin/env python3
"""Inspect database tables."""
import sqlite3
from pathlib import Path

db_path = Path.home() / ".dream-studio" / "state" / "studio.db"

conn = sqlite3.connect(db_path)

print("Tables in database:")
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for row in cursor.fetchall():
    print(f"  {row[0]}")

print("\nColumns in raw_research:")
cursor = conn.execute("PRAGMA table_info(raw_research)")
for row in cursor.fetchall():
    print(f"  {row[1]} ({row[2]})")

print("\nColumns in reg_research_sources:")
cursor = conn.execute("PRAGMA table_info(reg_research_sources)")
for row in cursor.fetchall():
    print(f"  {row[1]} ({row[2]})")

print("\nColumns in pi_waves:")
cursor = conn.execute("PRAGMA table_info(pi_waves)")
for row in cursor.fetchall():
    print(f"  {row[1]} ({row[2]})")

print("\nColumns in pi_wave_tasks:")
cursor = conn.execute("PRAGMA table_info(pi_wave_tasks)")
for row in cursor.fetchall():
    print(f"  {row[1]} ({row[2]})")

conn.close()
