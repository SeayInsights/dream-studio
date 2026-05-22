#!/usr/bin/env python3
"""Benchmark query performance for Track A refactor verification."""

import argparse
import sqlite3
import time
from pathlib import Path
from core.config.database import get_connection


def get_db_path():
    """Return canonical DB path."""
    home = Path.home()
    return home / ".dream-studio" / "state" / "studio.db"


def get_db_size(db_path):
    """Return DB size in MB."""
    return db_path.stat().st_size / (1024 * 1024)


def benchmark_query(conn, name, query):
    """Execute query and measure performance."""
    start = time.perf_counter()
    cursor = conn.execute(query)
    rows = cursor.fetchall()
    elapsed_ms = (time.perf_counter() - start) * 1000
    return {
        "name": name,
        "elapsed_ms": elapsed_ms,
        "row_count": len(rows),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true", help="Run baseline benchmark")
    args = parser.parse_args()

    db_path = get_db_path()
    if not db_path.exists():
        print(f"Error: DB not found at {db_path}")
        return 1

    db_size_mb = get_db_size(db_path)
    print(f"Database: {db_path}")
    print(f"Size: {db_size_mb:.2f} MB")
    print()

    conn = get_connection()

    # Common queries to benchmark
    queries = [
        (
            "canonical_events_recent",
            "SELECT * FROM canonical_events ORDER BY timestamp DESC LIMIT 100",
        ),
        ("canonical_events_count", "SELECT COUNT(*) FROM canonical_events"),
        (
            "guardrail_decisions",
            "SELECT * FROM guardrail_decisions ORDER BY created_at DESC LIMIT 50",
        ),
        ("skill_telemetry", "SELECT * FROM skill_telemetry ORDER BY timestamp DESC LIMIT 100"),
        ("hook_findings", "SELECT * FROM hook_findings WHERE severity = 'high' LIMIT 50"),
        (
            "automation_checkpoints",
            "SELECT * FROM automation_checkpoints ORDER BY created_at DESC LIMIT 50",
        ),
        ("token_usage", "SELECT SUM(total_tokens) FROM token_usage"),
    ]

    results = []
    print("Running benchmarks...\n")

    for name, query in queries:
        try:
            result = benchmark_query(conn, name, query)
            results.append(result)
            print(f"{name:30s} {result['elapsed_ms']:8.2f} ms  ({result['row_count']} rows)")
        except sqlite3.OperationalError as e:
            print(f"{name:30s} SKIPPED (table not found)")

    conn.close()

    print()
    avg_time = sum(r["elapsed_ms"] for r in results) / len(results) if results else 0
    max_time = max((r["elapsed_ms"] for r in results), default=0)
    print(f"Average query time: {avg_time:.2f} ms")
    print(f"Slowest query: {max_time:.2f} ms")
    print()

    # Performance assessment
    if max_time < 100:
        print("Performance: All queries <100ms (excellent)")
    elif max_time < 500:
        print("Performance: All queries <500ms (good)")
    else:
        print("Performance: Some queries >500ms (review needed)")

    return 0


if __name__ == "__main__":
    exit(main())
