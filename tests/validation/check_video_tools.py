import sqlite3
from pathlib import Path
from core.config.database import get_connection

db = Path.home() / ".dream-studio" / "state" / "studio.db"
conn = get_connection()

rows = conn.execute("""
    SELECT name, description, tags FROM tool_registry
    WHERE description LIKE '%video%'
       OR name LIKE '%video%'
       OR tags LIKE '%video%'
       OR description LIKE '%ffmpeg%'
       OR name LIKE '%ffmpeg%'
""").fetchall()

print(f"Found {len(rows)} video/ffmpeg-related tools:")
for name, desc, tags in rows[:15]:
    print(f"  {name}: {desc[:60]}... | Tags: {tags[:40]}")

conn.close()
