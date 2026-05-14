import sqlite3
from pathlib import Path
from core.config.database import get_connection

db = Path.home() / ".dream-studio" / "state" / "studio.db"
conn = get_connection()

# List all tables
tables = [
    t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
]
print(f"Tables ({len(tables)}):", tables)

# Check pi_components if it exists
if "pi_components" in tables:
    cols = [c[1] for c in conn.execute("PRAGMA table_info(pi_components)").fetchall()]
    print(f"\npi_components columns: {cols}")
else:
    print("\npi_components table does NOT exist")

conn.close()
