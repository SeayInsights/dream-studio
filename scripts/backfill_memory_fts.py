"""Backfill memory_fts from existing memory_entries rows.

Run when the FTS trigger was added after rows were already inserted.
"""
import os
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

db = os.path.expanduser("~/.dream-studio/state/studio.db")
c = sqlite3.connect(db)

trig = c.execute(
    "SELECT name FROM sqlite_master WHERE type='trigger' AND name='memory_entries_fts_insert'"
).fetchone()
print("FTS insert trigger exists:", bool(trig))

# Backfill
c.execute("DELETE FROM memory_fts")
c.execute(
    "INSERT INTO memory_fts(memory_id, content, category, tags)"
    " SELECT memory_id, content, category, COALESCE(tags, '') FROM memory_entries"
)
c.commit()

count = c.execute("SELECT COUNT(*) FROM memory_fts").fetchone()[0]
print(f"memory_fts after backfill: {count}")

# Smoke test
results = c.execute(
    "SELECT COUNT(*) FROM memory_fts WHERE memory_fts MATCH '\"tabindex\"'"
).fetchone()[0]
print(f"FTS search 'tabindex' results: {results}")

c.close()
print("Done.")
