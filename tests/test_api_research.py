"""API tests for research endpoints (Phase 7, T139).

Tests cover:
1. POST /api/discovery/research - Trigger web research
2. POST /api/discovery/research (cache hit) - Return cached results
3. GET /api/discovery/research/{topic} - Get cached research
4. DELETE /api/discovery/research/{topic} - Invalidate cache entry

Testing strategy:
- Mock WebSearch tool (no real API calls in tests)
- Use pytest fixtures for test database
- Test FastAPI client from TestClient
- Isolated test database for each test
"""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from projections.api.main import app
from control.research import web as web_research

# ============================================================================
# FIXTURES
# ============================================================================


def _mock_transaction(conn: sqlite3.Connection):
    @contextmanager
    def _txn(immediate=False):
        yield conn
        conn.commit()

    return _txn


@pytest.fixture
def test_db() -> Generator[Path, None, None]:
    """Create temporary database with research_cache table for testing.

    Creates research_cache table needed for research endpoints.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Create research_cache table (matching migration 013)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS research_cache (
                cache_id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                focus_areas TEXT,
                sources TEXT,
                findings TEXT,
                confidence_score REAL,
                triangulation_score REAL,
                created_at TEXT DEFAULT (datetime('now')),
                expires_at TEXT
            )
        """)

        conn.commit()
        conn.close()

        yield db_path

    finally:
        import gc
        import time

        gc.collect()

        for attempt in range(3):
            try:
                if db_path.exists():
                    db_path.unlink()
                break
            except PermissionError:
                if attempt < 2:
                    time.sleep(0.1)
                    gc.collect()


@pytest.fixture(autouse=True)
def _isolate_db(request):
    """Patch DB imports in web module to use isolated test_db for all tests.

    Only activates when a test requests the test_db fixture. Suppresses
    emit_event to prevent the event store from opening a competing transaction
    on the same file.
    """
    if "test_db" not in request.fixturenames:
        yield
        return

    test_db: Path = request.getfixturevalue("test_db")

    def _conn_factory():
        c = sqlite3.connect(str(test_db), check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    shared_conn = _conn_factory()

    with patch("control.research.web.get_connection", side_effect=_conn_factory), patch(
        "control.research.web.transaction", _mock_transaction(shared_conn)
    ), patch("control.research.web.emit_event"), patch(
        "core.event_store.studio_db._connect", side_effect=_conn_factory
    ), patch(
        "core.events.emitter.emit_event"
    ):
        yield

    shared_conn.close()


@pytest.fixture
def client() -> TestClient:
    """Create FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_websearch_results():
    """Sample WebSearch results for mocking."""
    return [
        {
            "url": "https://github.com/python/cpython/blob/main/Doc/library/asyncio.rst",
            "title": "asyncio — Asynchronous I/O — Python Documentation",
            "snippet": "The asyncio package provides infrastructure for writing single-threaded concurrent code using coroutines, multiplexing I/O access over sockets and other resources.",
        },
        {
            "url": "https://docs.python.org/3/library/asyncio.html",
            "title": "asyncio — Asynchronous I/O, event loop, coroutines and tasks",
            "snippet": "asyncio is used as a foundation for multiple Python asynchronous frameworks that provide high-performance network and web-servers, database connection libraries, distributed task queues.",
        },
        {
            "url": "https://realpython.com/async-io-python/",
            "title": "Async IO in Python: A Complete Walkthrough",
            "snippet": "This tutorial will give you a firm grasp of Python's approach to async IO, which is a concurrent programming design that has received dedicated support in Python.",
        },
        {
            "url": "https://stackoverflow.com/questions/49005651/how-does-asyncio-actually-work",
            "title": "How does asyncio actually work in Python?",
            "snippet": "asyncio is a library to write concurrent code using the async/await syntax. It's used as a foundation for multiple Python async frameworks.",
        },
        {
            "url": "https://medium.com/@niran.aladakatti/understanding-python-asyncio-5b3e4b4e3f3f",
            "title": "Understanding Python asyncio - Medium",
            "snippet": "Python's asyncio module provides infrastructure for writing single-threaded concurrent code using coroutines, multiplexing I/O access over sockets.",
        },
    ]


@pytest.fixture
def sample_report():
    """Sample ResearchReport for testing."""
    sources = [
        web_research.Source(
            url="https://github.com/python/cpython",
            title="Python GitHub",
            snippet="Official Python repository",
            tier=1,
        ),
        web_research.Source(
            url="https://realpython.com/python-async",
            title="Real Python Async Tutorial",
            snippet="Tutorial on async Python",
            tier=2,
        ),
        web_research.Source(
            url="https://stackoverflow.com/questions/123/async-python",
            title="Stack Overflow Async Question",
            snippet="Community Q&A on async",
            tier=3,
        ),
    ]

    return web_research.ResearchReport(
        topic="python async programming",
        sources=sources,
        findings="## Research Findings\n\n### Primary Sources (Tier 1)\n- **[Python GitHub](https://github.com/python/cpython)**\n  Official Python repository\n\n### Technical Content (Tier 2)\n- **[Real Python Async Tutorial](https://realpython.com/python-async)**\n  Tutorial on async Python\n\n### Community Discussion (Tier 3)\n- **[Stack Overflow Async Question](https://stackoverflow.com/questions/123/async-python)**\n  Community Q&A on async\n",
        confidence=0.76,
        triangulation=1.0,
    )


# ============================================================================
# API TESTS
# ============================================================================


def test_research_endpoint(client: TestClient, test_db: Path, mock_websearch_results):
    """Test POST /api/discovery/research - Trigger research, returns report.

    Steps:
    1. Mock WebSearch tool to return sample results
    2. POST research request with topic and focus_areas
    3. Verify response contains ResearchReport structure
    4. Verify confidence and triangulation scores are calculated
    5. Verify findings are generated
    """
    mock_sources = web_research.extract_sources(mock_websearch_results)

    with patch("control.research.web.search_web", return_value=mock_sources):
        response = client.post(
            "/api/discovery/research",
            json={"topic": "python async programming", "focus_areas": ["asyncio", "coroutines"]},
        )

    assert response.status_code == 200
    data = response.json()

    assert "topic" in data
    assert "sources" in data
    assert "findings" in data
    assert "confidence" in data
    assert "triangulation" in data

    assert data["topic"] == "python async programming"
    assert len(data["sources"]) == 5
    assert 0.0 <= data["confidence"] <= 1.0
    assert 0.0 <= data["triangulation"] <= 1.0
    assert isinstance(data["findings"], str)
    assert len(data["findings"]) > 0

    assert data["triangulation"] == 1.0
    assert data["confidence"] > 0.5


def test_research_cache_hit(client: TestClient, test_db: Path, sample_report):
    """Test POST /api/discovery/research (cache hit) - Second POST returns cached result.

    Steps:
    1. Save research report to cache
    2. Make POST request for same topic
    3. Verify response is from cache (no WebSearch call)
    4. Verify response data matches cached report
    """
    web_research.save_to_cache("python async programming", sample_report, ttl_days=30)

    with patch("control.research.web.search_web") as mock_search:
        mock_search.return_value = []

        response = client.post(
            "/api/discovery/research", json={"topic": "python async programming", "focus_areas": []}
        )

        mock_search.assert_not_called()

    assert response.status_code == 200
    data = response.json()

    assert data["topic"] == "python async programming"
    assert data["confidence"] == 0.76
    assert data["triangulation"] == 1.0
    assert len(data["sources"]) == 3


def test_get_cached_research(client: TestClient, test_db: Path, sample_report):
    """Test GET /api/discovery/research?topic={topic} - Returns saved report.

    Steps:
    1. Save research report to cache
    2. Make GET request for topic (query param)
    3. Verify response contains cached report
    4. Verify all fields match original report
    """
    web_research.save_to_cache("python async programming", sample_report, ttl_days=30)

    response = client.get("/api/discovery/research?topic=python%20async%20programming")

    assert response.status_code == 200
    data = response.json()

    assert data["topic"] == "python async programming"
    assert data["confidence"] == 0.76
    assert data["triangulation"] == 1.0
    assert len(data["sources"]) == 3

    for source in data["sources"]:
        assert "url" in source
        assert "title" in source
        assert "snippet" in source
        assert "tier" in source
        assert 1 <= source["tier"] <= 3


def test_get_cached_research_not_found(client: TestClient, test_db: Path):
    """Test GET /api/discovery/research?topic={topic} - 404 when not cached.

    Steps:
    1. Make GET request for non-existent topic
    2. Verify 404 response
    3. Verify error message
    """
    response = client.get("/api/discovery/research?topic=nonexistent%20topic")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data or "error" in data


def test_get_cached_research_expired(client: TestClient, test_db: Path, sample_report):
    """Test GET /api/discovery/research?topic={topic} - 404 when cache expired.

    Steps:
    1. Save report to cache with TTL
    2. Manually expire the cache entry
    3. Make GET request
    4. Verify 404 response (expired = not found)
    """
    web_research.save_to_cache("python async programming", sample_report, ttl_days=30)

    # Manually expire the entry via a direct connection to the test DB file
    conn = sqlite3.connect(str(test_db))
    past_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    conn.execute(
        "UPDATE research_cache SET expires_at = ? WHERE topic = ?",
        (past_date, "python async programming"),
    )
    conn.commit()
    conn.close()

    response = client.get("/api/discovery/research?topic=python%20async%20programming")

    assert response.status_code == 404


def test_invalidate_cache(client: TestClient, test_db: Path, sample_report):
    """Test DELETE /api/discovery/research/{cache_id} - Removes cache entry.

    Steps:
    1. Save research report to cache
    2. Get cache_id from saved entry
    3. Verify entry exists with GET by topic
    4. Make DELETE request with cache_id
    5. Verify 204 No Content response
    6. Verify GET now returns 404
    """
    web_research.save_to_cache("python async programming", sample_report, ttl_days=30)

    conn = sqlite3.connect(str(test_db))
    row = conn.execute(
        "SELECT cache_id FROM research_cache WHERE topic = ?", ("python async programming",)
    ).fetchone()
    cache_id = row[0]
    conn.close()

    get_response = client.get("/api/discovery/research?topic=python%20async%20programming")
    assert get_response.status_code == 200

    delete_response = client.delete(f"/api/discovery/research/{cache_id}")
    assert delete_response.status_code == 204

    get_after_delete = client.get("/api/discovery/research?topic=python%20async%20programming")
    assert get_after_delete.status_code == 404


def test_invalidate_cache_nonexistent(client: TestClient, test_db: Path):
    """Test DELETE /api/discovery/research/{cache_id} - Succeeds even if not cached.

    Steps:
    1. Make DELETE request for non-existent cache_id
    2. Verify 204 No Content response (idempotent)
    """
    response = client.delete("/api/discovery/research/nonexistent1234")
    assert response.status_code == 204


def test_research_endpoint_no_websearch_results(client: TestClient, test_db: Path):
    """Test POST /api/discovery/research - No sources found.

    Steps:
    1. Mock WebSearch to return empty results
    2. Make POST request
    3. Verify response contains empty sources
    4. Verify confidence = 0.0, triangulation = 0.0
    """
    with patch("control.research.web.search_web", return_value=[]):
        response = client.post(
            "/api/discovery/research", json={"topic": "obscure topic xyz", "focus_areas": []}
        )

    assert response.status_code == 200
    data = response.json()

    assert len(data["sources"]) == 0
    assert data["confidence"] == 0.0
    assert data["triangulation"] == 0.0
    assert "No sources found" in data["findings"]


def test_research_endpoint_validation_error(client: TestClient):
    """Test POST /api/discovery/research - Validation error for empty topic.

    Steps:
    1. Make POST request with empty topic
    2. Verify 422 Unprocessable Entity response
    """
    response = client.post("/api/discovery/research", json={"topic": "", "focus_areas": []})

    assert response.status_code == 422


def test_research_endpoint_missing_fields(client: TestClient):
    """Test POST /api/discovery/research - Validation error for missing fields.

    Steps:
    1. Make POST request without required fields
    2. Verify 422 Unprocessable Entity response
    """
    response = client.post("/api/discovery/research", json={})

    assert response.status_code == 422


def test_get_cached_research_by_cache_id(client: TestClient, test_db: Path, sample_report):
    """Test GET /api/discovery/research/{cache_id} - Returns saved report by cache_id.

    Steps:
    1. Save research report to cache
    2. Get cache_id from saved entry
    3. Make GET request with cache_id
    4. Verify response contains cached report
    """
    web_research.save_to_cache("python async programming", sample_report, ttl_days=30)

    conn = sqlite3.connect(str(test_db))
    row = conn.execute(
        "SELECT cache_id FROM research_cache WHERE topic = ?", ("python async programming",)
    ).fetchone()
    cache_id = row[0]
    conn.close()

    response = client.get(f"/api/discovery/research/{cache_id}")

    assert response.status_code == 200
    data = response.json()

    assert data["topic"] == "python async programming"
    assert data["confidence"] == 0.76
    assert data["triangulation"] == 1.0
    assert len(data["sources"]) == 3
    assert data["cache_id"] == cache_id


def test_get_cached_research_by_invalid_cache_id(client: TestClient, test_db: Path):
    """Test GET /api/discovery/research/{cache_id} - 404 for invalid cache_id.

    Steps:
    1. Make GET request with non-existent cache_id
    2. Verify 404 response
    """
    response = client.get("/api/discovery/research/invalidcacheid123")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


def test_research_endpoint_with_whitespace_topic(
    client: TestClient, test_db: Path, mock_websearch_results
):
    """Test POST /api/discovery/research - Topic with leading/trailing whitespace.

    Steps:
    1. POST with topic containing whitespace
    2. Verify request is processed correctly (whitespace trimmed)
    3. Verify cache lookup normalizes topic
    """
    mock_sources = web_research.extract_sources(mock_websearch_results)

    with patch("control.research.web.search_web", return_value=mock_sources):
        response = client.post(
            "/api/discovery/research", json={"topic": "  python async  ", "focus_areas": []}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["topic"] == "  python async  "  # Original topic preserved in response

    # Verify cache was saved with normalized key
    conn = sqlite3.connect(str(test_db))
    row = conn.execute(
        "SELECT topic FROM research_cache WHERE topic = ?", ("python async",)  # Normalized key
    ).fetchone()
    assert row is not None
    conn.close()
