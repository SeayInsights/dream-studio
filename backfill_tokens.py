"""Backfill token aggregation by project/model"""
import sqlite3
import os

db = os.path.expanduser("~/.dream-studio/state/studio.db")
conn = sqlite3.connect(db)
c = conn.cursor()

print("=== TOKEN BACKFILL ===\n")

# Aggregate tokens by project
c.execute("""
    UPDATE raw_token_usage
    SET project_id = (
        SELECT project_id FROM raw_sessions
        WHERE raw_sessions.session_id = raw_token_usage.session_id
        LIMIT 1
    )
    WHERE project_id IS NULL AND session_id IS NOT NULL
""")
print(f"Updated {c.rowcount} token records with project_id")

# Check aggregation
c.execute("""
    SELECT project_id, SUM(input_tokens + output_tokens) as total
    FROM raw_token_usage
    WHERE project_id IS NOT NULL
    GROUP BY project_id
    ORDER BY total DESC
    LIMIT 5
""")
print("\nTop 5 projects by tokens:")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]:,} tokens")

conn.commit()
conn.close()
print("\n✓ Backfill complete!")
