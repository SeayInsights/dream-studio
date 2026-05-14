"""Check actual schema of automation tables"""

import sqlite3
import os
from core.config.database import get_connection

db_path = os.path.expanduser("~/.dream-studio/state/studio.db")
if not os.path.exists(db_path):
    print(f"Error: Database not found at {db_path}")
    exit(1)

conn = get_connection()
cursor = conn.cursor()

# Check if tables exist
cursor.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND (name='automation_checkpoints' OR name='automation_log')"
)
tables = cursor.fetchall()

if not tables:
    print("No automation tables found in studio.db")
    conn.close()
    exit(0)

print("Found tables:", [t[0] for t in tables])
print()

# Get schema for each table
for table in tables:
    table_name = table[0]
    print(f"=== Schema for {table_name} ===")
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    for col in columns:
        cid, name, type_, notnull, dflt_value, pk = col
        print(f"  {name}: {type_} {'NOT NULL' if notnull else ''} {'PRIMARY KEY' if pk else ''}")

    # Get row count
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"  Row count: {count}")
    print()

conn.close()
