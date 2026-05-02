import sqlite3
import os

db_path = os.path.expanduser("~/.dream-studio/state/studio.db")
db = sqlite3.connect(db_path)
cursor = db.cursor()

# Get all tables
tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
print(f"Found {len(tables)} tables:")
for table in tables:
    count = cursor.execute(f"SELECT COUNT(*) FROM {table[0]}").fetchone()[0]
    print(f"  - {table[0]}: {count} rows")

db.close()
