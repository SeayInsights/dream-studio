"""Unit tests for web_research module with confidence scoring and source triangulation.

Tests cover:
- research_topic() with mocked WebSearch
- extract_sources() parsing WebSearch JSON
- calculate_confidence() weighted tier scoring
- calculate_triangulation() source count scoring
- Research cache hit/miss/expiry behavior
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, UTC
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from control.research import web as web_research


def _mock_transaction(conn):
    @contextmanager
    def _txn(immediate=False):
        yield conn

    return _txn


@pytest.fixture(autouse=True)
def disable_research_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Research logic tests should not write telemetry/events to native state."""
    monkeypatch.setattr(web_research, "_emit_metric", lambda *args, **kwargs: None)


# ── Test Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_search_results() -> list[dict]:
    """Create realistic WebSearch results with varied tier sources."""
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
def tier1_only_results() -> list[dict]:
    """WebSearch results with only tier 1 sources."""
    return [
        {
            "url": "https://github.com/python/cpython",
            "title": "Python/cpython - GitHub",
            "snippet": "The Python programming language official repository.",
        },
        {
            "url": "https://docs.python.org/3/",
            "title": "Python 3 Documentation",
            "snippet": "Official documentation for Python 3.",
        },
        {
            "url": "https://readthedocs.org/projects/python/",
            "title": "Python on Read the Docs",
            "snippet": "Python documentation hosted on Read the Docs.",
        },
    ]


@pytest.fixture
def tier3_only_results() -> list[dict]:
    """WebSearch results with only tier 3 sources."""
    return [
        {
            "url": "https://stackoverflow.com/questions/1234/python-question",
            "title": "Python Question - Stack Overflow",
            "snippet": "A question about Python on Stack Overflow.",
        },
        {
            "url": "https://www.reddit.com/r/Python/comments/abc123/",
            "title": "Python Discussion on Reddit",
            "snippet": "Community discussion about Python.",
        },
    ]


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database with research_cache table."""
    conn = sqlite3.connect(":memory:")
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
    return conn


@pytest.fixture
def sample_report() -> web_research.ResearchReport:
    """Create a sample ResearchReport for cache testing."""
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
        findings="## Research Findings\n\n### Primary Sources (Tier 1)\n- **[Python GitHub](https://github.com/python/cpython)**\n  Official Python repository\n",
        confidence=0.76,
        triangulation=1.0,
    )


# ── Tests ──────────────────────────────────────────────────────────────────


class TestExtractSources:
    """Test suite for extract_sources() parsing WebSearch JSON."""

    def test_extract_sources_mixed_tiers(self, mock_search_results):
        """Verify extract_sources parses results and assigns correct tiers."""
        sources = web_research.extract_sources(mock_search_results)

        assert len(sources) == 5

        # GitHub source should be tier 1
        github_source = next((s for s in sources if "github.com" in s.url), None)
        assert github_source is not None
        assert github_source.tier == 1

        # docs.python.org should be tier 1
        docs_source = next((s for s in sources if "docs.python.org" in s.url), None)
        assert docs_source is not None
        assert docs_source.tier == 1

        # Medium should be tier 2
        medium_source = next((s for s in sources if "medium.com" in s.url), None)
        assert medium_source is not None
        assert medium_source.tier == 2

        # Stack Overflow should be tier 3
        so_source = next((s for s in sources if "stackoverflow.com" in s.url), None)
        assert so_source is not None
        assert so_source.tier == 3

    def test_extract_sources_preserves_data(self, mock_search_results):
        """Verify all source fields are preserved correctly."""
        sources = web_research.extract_sources(mock_search_results)

        for i, source in enumerate(sources):
            original = mock_search_results[i]
            assert source.url == original["url"]
            assert source.title == original["title"]
            assert source.snippet == original["snippet"]
            assert source.tier in [1, 2, 3]

    def test_extract_sources_empty_list(self):
        """Empty search results should return empty source list."""
        sources = web_research.extract_sources([])
        assert sources == []

    def test_extract_sources_missing_fields(self):
        """Results with missing required fields should be skipped."""
        invalid_results = [
            {"url": "https://example.com"},  # Missing title
            {"title": "Example"},  # Missing url
            {"url": "", "title": "Empty URL", "snippet": "test"},  # Empty url
            {"url": "https://valid.com", "title": "Valid", "snippet": "good"},
        ]

        sources = web_research.extract_sources(invalid_results)

        # Only the last valid result should be included
        assert len(sources) == 1
        assert sources[0].url == "https://valid.com"

    def test_extract_sources_unknown_domain_defaults_tier2(self):
        """Unknown domains should default to tier 2."""
        results = [
            {"url": "https://unknown-blog.xyz/post", "title": "Unknown Blog", "snippet": "Test"}
        ]

        sources = web_research.extract_sources(results)

        assert len(sources) == 1
        assert sources[0].tier == 2


class TestCalculateConfidence:
    """Test suite for calculate_confidence() weighted tier scoring."""

    def test_calculate_confidence_all_tier1(self, tier1_only_results):
        """All tier 1 sources should yield 1.0 confidence."""
        sources = web_research.extract_sources(tier1_only_results)
        confidence = web_research.calculate_confidence(sources)

        assert confidence == 1.0

    def test_calculate_confidence_all_tier3(self, tier3_only_results):
        """All tier 3 sources should yield 0.3 confidence (tier 3 weight)."""
        sources = web_research.extract_sources(tier3_only_results)
        confidence = web_research.calculate_confidence(sources)

        # All tier 3: (2 * 0.3) / (2 * 1.0) = 0.6 / 2.0 = 0.3
        assert confidence == 0.3

    def test_calculate_confidence_mixed_tiers(self, mock_search_results):
        """Mixed tier sources should calculate weighted average correctly."""
        sources = web_research.extract_sources(mock_search_results)
        confidence = web_research.calculate_confidence(sources)

        # Expected breakdown (from fixture):
        # Tier 1: github.com, docs.python.org (2 sources * 1.0 = 2.0)
        # Tier 2: realpython.com, medium.com (2 sources * 0.6 = 1.2)
        # Tier 3: stackoverflow.com (1 source * 0.3 = 0.3)
        # Total weighted: 2.0 + 1.2 + 0.3 = 3.5
        # Max possible: 5 sources * 1.0 = 5.0
        # Confidence: 3.5 / 5.0 = 0.7

        assert confidence == 0.7

    def test_calculate_confidence_empty_sources(self):
        """Empty source list should return 0.0."""
        confidence = web_research.calculate_confidence([])
        assert confidence == 0.0

    def test_calculate_confidence_single_tier2_source(self):
        """Single tier 2 source should yield 0.6 confidence."""
        sources = [
            web_research.Source(
                url="https://blog.example.com/post", title="Blog Post", snippet="Test", tier=2
            )
        ]

        confidence = web_research.calculate_confidence(sources)

        # 1 * 0.6 / 1 * 1.0 = 0.6
        assert confidence == 0.6

    def test_calculate_confidence_rounds_to_two_decimals(self):
        """Confidence should round to 2 decimal places."""
        sources = [
            web_research.Source(url="https://a.com", title="A", snippet="", tier=1),
            web_research.Source(url="https://b.com", title="B", snippet="", tier=2),
            web_research.Source(url="https://c.com", title="C", snippet="", tier=3),
            web_research.Source(url="https://d.com", title="D", snippet="", tier=2),
            web_research.Source(url="https://e.com", title="E", snippet="", tier=3),
            web_research.Source(url="https://f.com", title="F", snippet="", tier=3),
            web_research.Source(url="https://g.com", title="G", snippet="", tier=1),
        ]

        confidence = web_research.calculate_confidence(sources)

        # Should have at most 2 decimal places
        decimal_part = str(confidence).split(".")[-1] if "." in str(confidence) else ""
        assert len(decimal_part) <= 2


class TestCalculateTriangulation:
    """Test suite for calculate_triangulation() source count scoring."""

    def test_calculate_triangulation_three_sources(self):
        """3 sources should yield 1.0 triangulation."""
        sources = [
            web_research.Source(
                url=f"https://example{i}.com", title=f"Source {i}", snippet="", tier=1
            )
            for i in range(3)
        ]

        triangulation = web_research.calculate_triangulation(sources)
        assert triangulation == 1.0

    def test_calculate_triangulation_more_than_three(self):
        """More than 3 sources should still yield 1.0."""
        sources = [
            web_research.Source(
                url=f"https://example{i}.com", title=f"Source {i}", snippet="", tier=1
            )
            for i in range(5)
        ]

        triangulation = web_research.calculate_triangulation(sources)
        assert triangulation == 1.0

    def test_calculate_triangulation_two_sources(self):
        """2 sources should yield 0.67 triangulation (2/3)."""
        sources = [
            web_research.Source(url="https://a.com", title="A", snippet="", tier=1),
            web_research.Source(url="https://b.com", title="B", snippet="", tier=1),
        ]

        triangulation = web_research.calculate_triangulation(sources)

        # 2/3 = 0.666... rounded to 0.67
        assert triangulation == 0.67

    def test_calculate_triangulation_one_source(self):
        """1 source should yield 0.33 triangulation (1/3)."""
        sources = [
            web_research.Source(url="https://a.com", title="A", snippet="", tier=1),
        ]

        triangulation = web_research.calculate_triangulation(sources)

        # 1/3 = 0.333... rounded to 0.33
        assert triangulation == 0.33

    def test_calculate_triangulation_empty_sources(self):
        """Empty source list should return 0.0."""
        triangulation = web_research.calculate_triangulation([])
        assert triangulation == 0.0

    def test_calculate_triangulation_rounds_to_two_decimals(self):
        """Triangulation should round to 2 decimal places."""
        sources = [
            web_research.Source(url="https://a.com", title="A", snippet="", tier=1),
        ]

        triangulation = web_research.calculate_triangulation(sources)

        # Should have at most 2 decimal places
        decimal_part = str(triangulation).split(".")[-1] if "." in str(triangulation) else ""
        assert len(decimal_part) <= 2


class TestResearchTopic:
    """Test suite for research_topic() with mocked WebSearch."""

    @patch("control.research.web.search_web")
    def test_research_topic_returns_report(self, mock_search, mock_search_results):
        """Verify research_topic returns ResearchReport with correct structure."""
        # Mock search_web to return parsed sources
        mock_search.return_value = web_research.extract_sources(mock_search_results)

        report = web_research.research_topic(
            topic="python async programming", focus_areas=["asyncio", "coroutines"]
        )

        assert isinstance(report, web_research.ResearchReport)
        assert report.topic == "python async programming"
        assert len(report.sources) == 5
        assert 0.0 <= report.confidence <= 1.0
        assert 0.0 <= report.triangulation <= 1.0
        assert isinstance(report.findings, str)
        assert len(report.findings) > 0

    @patch("control.research.web.search_web")
    def test_research_topic_calculates_metrics(self, mock_search, mock_search_results):
        """Verify confidence and triangulation are calculated correctly."""
        mock_search.return_value = web_research.extract_sources(mock_search_results)

        report = web_research.research_topic(topic="python async programming", focus_areas=[])

        # 5 sources = triangulation should be min(5/3, 1.0) = 1.0
        assert report.triangulation == 1.0

        # Mixed tier sources should yield reasonable confidence
        assert report.confidence > 0.5

    @patch("control.research.web.search_web")
    def test_research_topic_no_focus_areas(self, mock_search, mock_search_results):
        """Topic without focus areas should work."""
        mock_search.return_value = web_research.extract_sources(mock_search_results)

        report = web_research.research_topic(topic="machine learning", focus_areas=[])

        assert report.topic == "machine learning"
        mock_search.assert_called_once_with("machine learning")

    @patch("control.research.web.search_web")
    def test_research_topic_with_focus_areas(self, mock_search, mock_search_results):
        """Topic with focus areas should combine into query."""
        mock_search.return_value = web_research.extract_sources(mock_search_results)

        report = web_research.research_topic(topic="python", focus_areas=["asyncio", "performance"])

        assert report.topic == "python"
        mock_search.assert_called_once_with("python asyncio performance")

    @patch("control.research.web.search_web")
    def test_research_topic_no_sources(self, mock_search):
        """Research with no sources should return valid report."""
        mock_search.return_value = []

        report = web_research.research_topic(topic="obscure topic xyz", focus_areas=[])

        assert report.topic == "obscure topic xyz"
        assert report.sources == []
        assert report.confidence == 0.0
        assert report.triangulation == 0.0
        assert "No sources found" in report.findings


class TestResearchCache:
    """Test suite for research cache hit/miss/expiry behavior."""

    @pytest.fixture(autouse=True)
    def _patch_db(self, test_db):
        with (
            patch("control.research.web.get_connection", return_value=test_db),
            patch("control.research.web.transaction", _mock_transaction(test_db)),
        ):
            yield

    def test_save_to_cache_success(self, test_db, sample_report):
        """Verify save_to_cache stores report correctly."""
        web_research.save_to_cache("python async", sample_report, ttl_days=30)

        row = test_db.execute(
            "SELECT topic, confidence_score, triangulation_score FROM research_cache WHERE topic = ?",
            ("python async",),
        ).fetchone()

        assert row is not None
        assert row[0] == "python async"
        assert row[1] == 0.76
        assert row[2] == 1.0

    def test_save_to_cache_normalizes_topic(self, test_db, sample_report):
        """Cache key should be lowercased and trimmed."""
        web_research.save_to_cache("  Python ASYNC  ", sample_report, ttl_days=30)

        row = test_db.execute("SELECT topic FROM research_cache").fetchone()

        assert row[0] == "python async"

    def test_save_to_cache_replaces_existing(self, test_db, sample_report):
        """Saving same topic twice should replace old entry."""
        web_research.save_to_cache("python async", sample_report, ttl_days=30)

        updated_report = web_research.ResearchReport(
            topic="python async",
            sources=sample_report.sources,
            findings="Updated findings",
            confidence=0.9,
            triangulation=1.0,
        )
        web_research.save_to_cache("python async", updated_report, ttl_days=30)

        rows = test_db.execute(
            "SELECT COUNT(*) FROM research_cache WHERE topic = ?", ("python async",)
        ).fetchone()

        assert rows[0] == 1

    def test_save_to_cache_empty_topic_raises(self, test_db, sample_report):
        """Empty topic should raise ValueError."""
        with pytest.raises(ValueError, match="Topic cannot be empty"):
            web_research.save_to_cache("", sample_report)

    def test_save_to_cache_negative_ttl_raises(self, test_db, sample_report):
        """Negative TTL should raise ValueError."""
        with pytest.raises(ValueError, match="TTL days must be non-negative"):
            web_research.save_to_cache("python async", sample_report, ttl_days=-1)

    def test_load_from_cache_hit(self, test_db, sample_report):
        """Cache hit should return stored report."""
        web_research.save_to_cache("python async", sample_report, ttl_days=30)

        loaded = web_research.load_from_cache("python async")

        assert loaded is not None
        assert loaded.topic == "python async"
        assert loaded.confidence == 0.76
        assert loaded.triangulation == 1.0
        assert len(loaded.sources) == 3

    def test_load_from_cache_miss(self, test_db):
        """Cache miss should return None."""
        loaded = web_research.load_from_cache("nonexistent topic")
        assert loaded is None

    def test_load_from_cache_expired(self, test_db, sample_report):
        """Expired cache entry should return None."""
        web_research.save_to_cache("python async", sample_report, ttl_days=30)

        past_date = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        test_db.execute(
            "UPDATE research_cache SET expires_at = ? WHERE topic = ?", (past_date, "python async")
        )

        loaded = web_research.load_from_cache("python async")
        assert loaded is None

    def test_load_from_cache_normalizes_topic(self, test_db, sample_report):
        """Cache lookup should normalize topic key."""
        web_research.save_to_cache("python async", sample_report, ttl_days=30)

        loaded = web_research.load_from_cache("  PYTHON Async  ")

        assert loaded is not None
        assert loaded.topic == "  PYTHON Async  "

    def test_load_from_cache_empty_topic_returns_none(self, test_db):
        """Empty topic should return None gracefully."""
        loaded = web_research.load_from_cache("")
        assert loaded is None

    def test_invalidate_cache_success(self, test_db, sample_report):
        """Invalidate should delete cache entry."""
        web_research.save_to_cache("python async", sample_report, ttl_days=30)

        web_research.invalidate_cache("python async")

        loaded = web_research.load_from_cache("python async")
        assert loaded is None

    def test_invalidate_cache_nonexistent(self, test_db):
        """Invalidating non-existent topic should succeed silently."""
        web_research.invalidate_cache("nonexistent")

    def test_invalidate_cache_empty_topic(self, test_db):
        """Empty topic invalidate should succeed silently."""
        web_research.invalidate_cache("")


class TestJinaIntegration:
    """Test suite for Jina Search API integration."""

    def test_jina_search(self):
        """Test Jina search with mocked API response."""
        # Mock Jina API response
        mock_jina_response = {
            "results": [
                {
                    "url": "https://github.com/python/cpython",
                    "title": "CPython Official Repository",
                    "snippet": "Official Python repository",
                    "relevance_score": 0.95,
                },
                {
                    "url": "https://docs.python.org/3/",
                    "title": "Python 3 Documentation",
                    "snippet": "Official Python documentation",
                    "relevance_score": 0.92,
                },
                {
                    "url": "https://realpython.com/python-guide",
                    "title": "Real Python Guide",
                    "snippet": "Comprehensive Python tutorial",
                    "relevance_score": 0.78,
                },
                {
                    "url": "https://stackoverflow.com/questions/python",
                    "title": "Stack Overflow Python Questions",
                    "snippet": "Community Q&A on Python",
                    "relevance_score": 0.65,
                },
            ]
        }

        with patch.dict("os.environ", {"JINA_API_KEY": "test-api-key"}):
            with patch("requests.post") as mock_post:
                mock_response = mock_post.return_value
                mock_response.json.return_value = mock_jina_response
                mock_response.raise_for_status.return_value = None

                sources = web_research.search_jina("python programming")

                # Verify all results were parsed
                assert len(sources) == 4

                # Verify sources have correct data
                assert sources[0].url == "https://github.com/python/cpython"
                assert sources[0].title == "CPython Official Repository"
                assert sources[0].snippet == "Official Python repository"

                # Verify API was called with correct parameters
                mock_post.assert_called_once()
                call_args = mock_post.call_args
                assert call_args[0][0] == "https://api.jina.ai/v1/search"
                assert call_args[1]["headers"]["Authorization"] == "Bearer test-api-key"
                assert call_args[1]["json"]["query"] == "python programming"
                assert call_args[1]["json"]["limit"] == 10

    def test_jina_source_tiers(self):
        """Test tier mapping from Jina relevance scores."""
        # Mock Jina API response with different relevance scores
        mock_jina_response = {
            "results": [
                {
                    "url": "https://github.com/high-score",
                    "title": "High Relevance Source",
                    "snippet": "Very relevant",
                    "relevance_score": 0.95,  # Should be Tier 1
                },
                {
                    "url": "https://blog.medium-score",
                    "title": "Medium Relevance Source",
                    "snippet": "Somewhat relevant",
                    "relevance_score": 0.80,  # Should be Tier 2 (0.7-0.9)
                },
                {
                    "url": "https://forum.low-score",
                    "title": "Low Relevance Source",
                    "snippet": "Barely relevant",
                    "relevance_score": 0.60,  # Should be Tier 3
                },
                {
                    "url": "https://example.boundary1",
                    "title": "Boundary Score 0.9",
                    "snippet": "Boundary test",
                    "relevance_score": 0.90,  # Boundary: should be Tier 2 (>0.9 is Tier 1)
                },
                {
                    "url": "https://example.boundary2",
                    "title": "Boundary Score 0.7",
                    "snippet": "Boundary test",
                    "relevance_score": 0.70,  # Boundary: should be Tier 2 (>=0.7)
                },
            ]
        }

        with patch.dict("os.environ", {"JINA_API_KEY": "test-api-key"}):
            with patch("requests.post") as mock_post:
                mock_response = mock_post.return_value
                mock_response.json.return_value = mock_jina_response
                mock_response.raise_for_status.return_value = None

                sources = web_research.search_jina("test query")

                # Verify tier mappings
                assert sources[0].tier == 1, "Score 0.95 should map to Tier 1"
                assert sources[1].tier == 2, "Score 0.80 should map to Tier 2"
                assert sources[2].tier == 3, "Score 0.60 should map to Tier 3"
                assert sources[3].tier == 2, "Score 0.90 should map to Tier 2 (boundary)"
                assert sources[4].tier == 2, "Score 0.70 should map to Tier 2 (boundary)"

    def test_jina_fallback(self):
        """Test fallback to WebSearch when JINA_API_KEY missing."""
        # Test with missing API key
        with patch.dict("os.environ", {}, clear=True):
            sources = web_research.search_jina("python programming")

            # Should return empty list when API key is missing
            assert sources == []

            # Verify no API call was made
            # (no need to mock requests since we should exit early)

    def test_jina_fallback_with_search_web(self):
        """Test research_topic falls back to WebSearch when Jina returns no results."""
        mock_search_results = [
            {
                "url": "https://github.com/python",
                "title": "Python Repository",
                "snippet": "Python official repo",
            }
        ]

        with patch.dict("os.environ", {}, clear=True):
            with patch("control.research.web.search_jina") as mock_jina:
                with patch("control.research.web.search_web") as mock_websearch:
                    # Jina returns empty (no API key), WebSearch should be called
                    mock_jina.return_value = []
                    mock_websearch.return_value = web_research.extract_sources(mock_search_results)

                    report = web_research.research_topic(topic="python programming", focus_areas=[])

                    # Verify Jina was attempted
                    mock_jina.assert_called_once()

                    # Verify WebSearch fallback was called
                    mock_websearch.assert_called_once()

                    # Verify report was generated from WebSearch results
                    assert len(report.sources) == 1
                    assert report.sources[0].url == "https://github.com/python"

    def test_jina_api_error_returns_empty(self):
        """Test that Jina API errors result in empty list."""
        with patch.dict("os.environ", {"JINA_API_KEY": "test-key"}):
            with patch("requests.post") as mock_post:
                # Simulate API error
                mock_post.side_effect = Exception("API connection failed")

                sources = web_research.search_jina("python")

                # Should return empty list on error
                assert sources == []

    def test_jina_missing_result_fields(self):
        """Test Jina handles results with missing fields gracefully."""
        mock_jina_response = {
            "results": [
                {
                    "url": "https://github.com/valid",
                    "title": "Valid Result",
                    "snippet": "Good snippet",
                    "relevance_score": 0.9,
                },
                {
                    # Missing title - should be skipped
                    "url": "https://example.com/no-title",
                    "snippet": "Has snippet",
                    "relevance_score": 0.8,
                },
                {
                    # Missing url - should be skipped
                    "title": "No URL Result",
                    "snippet": "Has snippet",
                    "relevance_score": 0.7,
                },
                {
                    # Valid but no relevance_score defaults to 0.0
                    "url": "https://example.com/no-score",
                    "title": "No Score Result",
                    "snippet": "Test",
                },
            ]
        }

        with patch.dict("os.environ", {"JINA_API_KEY": "test-key"}):
            with patch("requests.post") as mock_post:
                mock_response = mock_post.return_value
                mock_response.json.return_value = mock_jina_response
                mock_response.raise_for_status.return_value = None

                sources = web_research.search_jina("test")

                # Should have 2 valid results (first one, and fourth with default score)
                assert len(sources) == 2
                assert sources[0].url == "https://github.com/valid"
                assert sources[1].url == "https://example.com/no-score"
                # No score defaults to 0.0, which is < 0.7, so Tier 3
                assert sources[1].tier == 3
