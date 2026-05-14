#!/usr/bin/env python3
"""Legacy opt-in diagnostic for research trust scores.

This script inspects local research evidence tables. It is not part of normal
validation, is not a research authority surface, and must not be run against the
native runtime DB unless the operator explicitly opts in.
"""

from __future__ import annotations

import os
import sys

from core.event_store.studio_db import _connect

OPT_IN_ENV = "DREAM_STUDIO_RUN_LEGACY_RESEARCH_DIAGNOSTICS"


def _require_opt_in() -> None:
    if os.environ.get(OPT_IN_ENV) == "1":
        return
    print(
        f"Refusing to inspect local research DB state without {OPT_IN_ENV}=1. "
        "Use an isolated temp DB for diagnostics whenever possible.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def main() -> int:
    _require_opt_in()

    conn = _connect()
    try:
        print("Raw research records:")
        cursor = conn.execute(
            "SELECT research_id, query, source_url, trust_score, validation_status "
            "FROM raw_research WHERE query LIKE '%Next.js%'"
        )
        for row in cursor.fetchall():
            print(
                f"  research_id={row[0]}, query={row[1][:30]}..., "
                f"source={row[2]}, trust={row[3]}, status={row[4]}"
            )

        print("\nResearch sources:")
        cursor = conn.execute(
            "SELECT source_url, trust_score, total_queries, successful_queries, "
            "failed_queries FROM reg_research_sources"
        )
        for row in cursor.fetchall():
            print(
                f"  source={row[0]}, trust={row[1]}, total={row[2]}, "
                f"success={row[3]}, fail={row[4]}"
            )
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
