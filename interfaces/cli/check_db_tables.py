import sqlite3
from pathlib import Path
from core.config.database import get_connection

db_path = Path.home() / ".dream-studio" / "studio.db"
conn = get_connection()
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [t[0] for t in cursor.fetchall()]

print(f"Tables in {db_path}:")
for table in tables:
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    count = cursor.fetchone()[0]
    print(f"  {table}: {count} rows")

conn.close()
