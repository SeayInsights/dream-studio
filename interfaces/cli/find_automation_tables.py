import sqlite3
from pathlib import Path
from core.config.database import get_connection

# Check state/studio.db
db_path = Path.home() / ".dream-studio" / "state" / "studio.db"
if db_path.exists():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE '%automation%') ORDER BY name"
    )
    tables = [t[0] for t in cursor.fetchall()]

    print(f"Automation tables in {db_path}:")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"  {table}: {count} rows")

    conn.close()
else:
    print(f"Database not found: {db_path}")
