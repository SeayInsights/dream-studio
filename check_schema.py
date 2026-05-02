import sqlite3
import os

db_path = os.path.expanduser("~/.dream-studio/state/studio.db")
db = sqlite3.connect(db_path)
cursor = db.cursor()

# Get raw_sessions schema
print("raw_sessions columns:")
for row in cursor.execute("PRAGMA table_info(raw_sessions)").fetchall():
    print(f"  {row[1]:30} {row[2]:15} {'NOT NULL' if row[3] else ''}")

# Get first row as example
print("\nFirst row:")
cursor.execute("SELECT * FROM raw_sessions LIMIT 1")
row = cursor.fetchone()
if row:
    cols = [desc[0] for desc in cursor.description]
    for col, val in zip(cols, row):
        print(f"  {col}: {val}")

db.close()
