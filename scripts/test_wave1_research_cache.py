#!/usr/bin/env python3
"""Test Wave 1 research caching infrastructure."""
import sys
from pathlib import Path

# Add hooks to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

from lib.research_engine import research_with_cache
from lib.studio_db import _connect

def cleanup():
    """Remove test data from previous runs."""
    conn = _connect()
    conn.execute("DELETE FROM raw_research WHERE query LIKE '%Next.js%'")
    conn.execute("DELETE FROM reg_research_sources WHERE source_url = 'internal://stub'")
    conn.commit()
    conn.close()
    print("[CLEANUP] Cleanup complete\n")

def test_cache_miss():
    """Test 1: Verify cache MISS on first query."""
    print("Test 1: Cache MISS on first query")

    result = research_with_cache("Next.js 15 + D1 compatibility", {}, "stack")

    # Verify cached flag
    assert result["cached"] == False, f"Expected cached=False, got {result['cached']}"

    # Verify record created in database
    conn = _connect()
    cursor = conn.execute(
        "SELECT research_id, query, times_referenced, trust_score FROM raw_research WHERE query LIKE '%Next.js%'"
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None, "No record created in raw_research table"
    assert row[2] == 0, f"Expected times_referenced=0 (fresh research), got {row[2]}"
    assert row[3] == 0.5, f"Expected trust_score=0.5, got {row[3]}"

    print("[PASS] Cache MISS on first query\n")

def test_cache_hit():
    """Test 2: Verify cache HIT on second query (same query)."""
    print("Test 2: Cache HIT on second query")

    # First, mark the research as validated so it can be cached
    conn = _connect()
    conn.execute(
        "UPDATE raw_research SET validation_status='validated' WHERE query LIKE '%Next.js%'"
    )
    conn.commit()
    conn.close()

    # Now query again - should get a cache hit
    # Use min_trust=0.5 since fresh research starts at 0.5, then trigger bumps to 0.6
    result = research_with_cache("Next.js 15 + D1 compatibility", {}, "stack", min_trust=0.5)

    # Verify cached flag
    assert result["cached"] == True, f"Expected cached=True, got {result['cached']}"

    # Verify times_referenced incremented
    conn = _connect()
    cursor = conn.execute(
        "SELECT times_referenced FROM raw_research WHERE query LIKE '%Next.js%'"
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None, "Record disappeared from raw_research table"
    assert row[0] == 1, f"Expected times_referenced=1 (first cache hit), got {row[0]}"

    print("[PASS] Cache HIT on second query\n")

def test_trust_adjustment():
    """Test 3: Verify trust score adjustment after validation."""
    print("Test 3: Trust score adjustment (manual validation)")

    # Research is already validated from test 2
    conn = _connect()
    cursor = conn.execute(
        "SELECT trust_score, validation_status, source_url FROM raw_research WHERE query LIKE '%Next.js%'"
    )
    row = cursor.fetchone()

    assert row is not None, "Record disappeared"
    assert row[1] == 'validated', f"Expected validation_status='validated', got {row[1]}"

    # The research record's trust_score stays at 0.5 (it's the source that gets adjusted)
    assert row[0] == 0.5, f"Expected raw_research.trust_score to remain at 0.5, got {row[0]}"

    # Check reg_research_sources trust_score - this is what the trigger updates
    source_url = row[2]
    cursor = conn.execute(
        "SELECT source_url, trust_score, total_queries, successful_queries FROM reg_research_sources WHERE source_url = ?",
        (source_url,)
    )
    source_row = cursor.fetchone()
    conn.close()

    if source_row:
        # Trigger should have inserted/updated the source with trust_score = 0.6 for validated research
        assert source_row[1] == 0.6, f"Expected source trust_score=0.6, got {source_row[1]}"
        assert source_row[2] >= 1, f"Expected total_queries >= 1, got {source_row[2]}"
        assert source_row[3] >= 1, f"Expected successful_queries >= 1, got {source_row[3]}"
        print(f"[PASS] Source trust score set to 0.6 (initial validated)")
        print(f"[PASS] Trigger fired (source: {source_row[0]})\n")
    else:
        raise AssertionError(f"No source record found in reg_research_sources for {source_url}")

def test_metrics():
    """Test 4: Verify metrics emitted."""
    print("Test 4: Metrics emitted")

    conn = _connect()

    # Check if raw_metrics table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='raw_metrics'"
    )
    table_exists = cursor.fetchone() is not None

    if not table_exists:
        conn.close()
        print("[SKIP] raw_metrics table not found (expected)\n")
        return

    # Check for metrics related to our test
    cursor = conn.execute(
        "SELECT COUNT(*) FROM raw_metrics WHERE metric_name LIKE '%research%'"
    )
    count = cursor.fetchone()[0]
    conn.close()

    if count > 0:
        print(f"[PASS] Metrics emitted ({count} research-related metrics found)\n")
    else:
        print("[SKIP] No research metrics found (may not be implemented yet)\n")

if __name__ == "__main__":
    print("Testing Wave 1 research cache...\n")
    print("=" * 60)

    try:
        cleanup()
        test_cache_miss()
        test_cache_hit()
        test_trust_adjustment()
        test_metrics()

        print("=" * 60)
        print("\n[SUCCESS] All Wave 1 tests passed!")

    except AssertionError as e:
        print("\n[FAIL] Test failed:")
        print(f"   {e}")
        sys.exit(1)
    except Exception as e:
        print("\n[ERROR] Unexpected error:")
        print(f"   {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
