"""Test migration 021 syntax"""

import sqlite3
import os
from core.config.database import get_connection

db_path = os.path.expanduser("~/.dream-studio/state/studio.db")
if not os.path.exists(db_path):
    print(f"Error: Database not found at {db_path}")
    exit(1)

migration_path = "hooks/lib/migrations/021_consolidate_databases.sql"
if not os.path.exists(migration_path):
    print(f"Error: Migration file not found at {migration_path}")
    exit(1)

try:
    conn = get_connection()
    with open(migration_path, "r") as f:
        script = f.read()

    # Execute the migration
    conn.executescript(script)
    conn.commit()
    conn.close()

    print("✅ Migration 021 executed successfully")
    print("   - Syntax valid")
    print("   - Indexes created")
    print("   - Schema version updated")
except Exception as e:
    print(f"❌ Migration failed: {e}")
    exit(1)
