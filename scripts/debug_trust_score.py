#!/usr/bin/env python3
"""Debug trust score calculation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

from lib.studio_db import _connect

conn = _connect()

print("Raw research records:")
cursor = conn.execute(
    "SELECT research_id, query, source_url, trust_score, validation_status FROM raw_research WHERE query LIKE '%Next.js%'"
)
for row in cursor.fetchall():
    print(f"  research_id={row[0]}, query={row[1][:30]}..., source={row[2]}, trust={row[3]}, status={row[4]}")

print("\nResearch sources:")
cursor = conn.execute(
    "SELECT source_url, trust_score, total_queries, successful_queries, failed_queries FROM reg_research_sources"
)
for row in cursor.fetchall():
    print(f"  source={row[0]}, trust={row[1]}, total={row[2]}, success={row[3]}, fail={row[4]}")

conn.close()
