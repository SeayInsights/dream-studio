"""Unit tests for tool_search TF-IDF search module.

Tests cover:
- TF-IDF index building
- Tool search functionality
- Confidence score calculation
- Category filtering
- Search caching and edge cases
- Semantic search with embeddings
- Hybrid search (TF-IDF + embeddings)
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Stub sentence_transformers if not installed so patch() can find the module
if "sentence_transformers" not in sys.modules:
    import types as _types
    _st_stub = _types.ModuleType("sentence_transformers")
    _st_stub.SentenceTransformer = MagicMock  # type: ignore[attr-defined]
    sys.modules["sentence_transformers"] = _st_stub

from control.research import tools as tool_search
from core.config.database import get_connection, transaction


@contextmanager
def _test_db_transaction(conn):
    """Test-specific transaction context manager for in-memory databases.

    Args:
        conn: SQLite connection to use for the transaction

    Yields:
        The same connection within a transaction context
    """
    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ── Test Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_tool_data() -> List[dict]:
    """Create 20 test tools with realistic descriptions."""
    return [
        {
            "tool_id": "1",
            "name": "ffmpeg-python",
            "category": "python_package",
            "description": "Video processing library for encoding, decoding, and streaming video files",
            "source_url": "https://github.com/kkroening/ffmpeg-python",
            "install_command": "pip install ffmpeg-python",
            "tags": json.dumps(["video", "encoding", "multimedia"]),
            "confidence_score": 0.95,
        },
        {
            "tool_id": "2",
            "name": "OpenCV",
            "category": "python_package",
            "description": "Computer vision library for image processing and video analysis",
            "source_url": "https://github.com/opencv/opencv",
            "install_command": "pip install opencv-python",
            "tags": json.dumps(["video", "image", "cv"]),
            "confidence_score": 0.92,
        },
        {
            "tool_id": "3",
            "name": "Pillow",
            "category": "python_package",
            "description": "Image processing library for creating, editing, and manipulating images",
            "source_url": "https://github.com/python-pillow/Pillow",
            "install_command": "pip install Pillow",
            "tags": json.dumps(["image", "graphics"]),
            "confidence_score": 0.88,
        },
        {
            "tool_id": "4",
            "name": "NumPy",
            "category": "python_package",
            "description": "Numerical computing library for array operations and mathematical functions",
            "source_url": "https://github.com/numpy/numpy",
            "install_command": "pip install numpy",
            "tags": json.dumps(["math", "numerics", "scientific"]),
            "confidence_score": 0.98,
        },
        {
            "tool_id": "5",
            "name": "mcp-git",
            "category": "mcp",
            "description": "MCP server for Git repository management and version control operations",
            "source_url": "https://github.com/modelcontextprotocol/servers/git",
            "install_command": "pip install mcp-git",
            "tags": json.dumps(["git", "vcs", "mcp"]),
            "confidence_score": 0.90,
        },
        {
            "tool_id": "6",
            "name": "mcp-filesystem",
            "category": "mcp",
            "description": "MCP server for file system operations including read, write, and directory traversal",
            "source_url": "https://github.com/modelcontextprotocol/servers/filesystem",
            "install_command": "pip install mcp-filesystem",
            "tags": json.dumps(["filesystem", "files", "mcp"]),
            "confidence_score": 0.89,
        },
        {
            "tool_id": "7",
            "name": "mcp-web",
            "category": "mcp",
            "description": "MCP server for web scraping, URL fetching, and HTTP request handling",
            "source_url": "https://github.com/modelcontextprotocol/servers/web",
            "install_command": "pip install mcp-web",
            "tags": json.dumps(["web", "http", "scraping", "mcp"]),
            "confidence_score": 0.87,
        },
        {
            "tool_id": "8",
            "name": "Requests",
            "category": "python_package",
            "description": "HTTP library for making web requests and API calls with simple interface",
            "source_url": "https://github.com/psf/requests",
            "install_command": "pip install requests",
            "tags": json.dumps(["http", "api", "web"]),
            "confidence_score": 0.96,
        },
        {
            "tool_id": "9",
            "name": "Django",
            "category": "python_package",
            "description": "Web framework for building full-featured web applications and REST APIs",
            "source_url": "https://github.com/django/django",
            "install_command": "pip install django",
            "tags": json.dumps(["web", "framework", "api"]),
            "confidence_score": 0.94,
        },
        {
            "tool_id": "10",
            "name": "Flask",
            "category": "python_package",
            "description": "Lightweight web framework for building simple web applications and microservices",
            "source_url": "https://github.com/pallets/flask",
            "install_command": "pip install flask",
            "tags": json.dumps(["web", "framework", "microservice"]),
            "confidence_score": 0.91,
        },
        {
            "tool_id": "11",
            "name": "PostgreSQL",
            "category": "api",
            "description": "Relational database system for storing and querying structured data",
            "source_url": "https://www.postgresql.org",
            "install_command": "brew install postgresql",
            "tags": json.dumps(["database", "sql"]),
            "confidence_score": 0.85,
        },
        {
            "tool_id": "12",
            "name": "Redis",
            "category": "api",
            "description": "In-memory data structure store for caching and fast data access",
            "source_url": "https://redis.io",
            "install_command": "brew install redis",
            "tags": json.dumps(["cache", "database", "memory"]),
            "confidence_score": 0.86,
        },
        {
            "tool_id": "13",
            "name": "MongoDB",
            "category": "saas",
            "description": "NoSQL document database for flexible schema and scalable data storage",
            "source_url": "https://www.mongodb.com",
            "install_command": None,
            "tags": json.dumps(["database", "nosql", "document"]),
            "confidence_score": 0.84,
        },
        {
            "tool_id": "14",
            "name": "TensorFlow",
            "category": "python_package",
            "description": "Machine learning framework for deep learning and neural network development",
            "source_url": "https://github.com/tensorflow/tensorflow",
            "install_command": "pip install tensorflow",
            "tags": json.dumps(["ml", "ai", "deep learning"]),
            "confidence_score": 0.93,
        },
        {
            "tool_id": "15",
            "name": "PyTorch",
            "category": "python_package",
            "description": "Deep learning framework with dynamic computation graphs for AI research",
            "source_url": "https://github.com/pytorch/pytorch",
            "install_command": "pip install torch",
            "tags": json.dumps(["ml", "ai", "deep learning"]),
            "confidence_score": 0.92,
        },
        {
            "tool_id": "16",
            "name": "Scikit-learn",
            "category": "python_package",
            "description": "Machine learning library with algorithms for classification, regression, and clustering",
            "source_url": "https://github.com/scikit-learn/scikit-learn",
            "install_command": "pip install scikit-learn",
            "tags": json.dumps(["ml", "classification", "regression"]),
            "confidence_score": 0.90,
        },
        {
            "tool_id": "17",
            "name": "Pandas",
            "category": "python_package",
            "description": "Data manipulation and analysis library with DataFrames for data wrangling",
            "source_url": "https://github.com/pandas-dev/pandas",
            "install_command": "pip install pandas",
            "tags": json.dumps(["data", "analysis", "dataframe"]),
            "confidence_score": 0.97,
        },
        {
            "tool_id": "18",
            "name": "Matplotlib",
            "category": "python_package",
            "description": "Visualization library for creating static, animated, and interactive plots",
            "source_url": "https://github.com/matplotlib/matplotlib",
            "install_command": "pip install matplotlib",
            "tags": json.dumps(["visualization", "plotting", "graphs"]),
            "confidence_score": 0.89,
        },
        {
            "tool_id": "19",
            "name": "Pytest",
            "category": "python_package",
            "description": "Testing framework for writing and running unit and integration tests",
            "source_url": "https://github.com/pytest-dev/pytest",
            "install_command": "pip install pytest",
            "tags": json.dumps(["testing", "unittest", "qa"]),
            "confidence_score": 0.91,
        },
        {
            "tool_id": "20",
            "name": "Docker",
            "category": "api",
            "description": "Containerization platform for packaging and deploying applications",
            "source_url": "https://www.docker.com",
            "install_command": "brew install docker",
            "tags": json.dumps(["devops", "container", "deployment"]),
            "confidence_score": 0.88,
        },
    ]


class NonClosingConnection:
    """Wrapper around sqlite3.Connection that ignores close() calls.

    Needed for tests that call close() multiple times on the same connection.
    """

    def __init__(self, conn):
        self._conn = conn

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def close(self):
        pass  # No-op instead of actually closing

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def in_memory_db(mock_tool_data):
    """Create an in-memory SQLite database with test tool_registry data."""
    # Create a fresh in-memory database for testing (isolated from shared connection)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create tool_registry table
    conn.execute("""
        CREATE TABLE tool_registry (
            tool_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            source_url TEXT,
            install_command TEXT,
            tags TEXT,
            confidence_score REAL
        )
    """)

    # Create tool_embeddings_cache table (for semantic search tests)
    conn.execute("""
        CREATE TABLE tool_embeddings_cache (
            tool_id TEXT PRIMARY KEY,
            embedding BLOB NOT NULL,
            model_name TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (tool_id) REFERENCES tool_registry(tool_id) ON DELETE CASCADE
        )
    """)

    # Insert test data using transaction pattern
    with _test_db_transaction(conn) as txn:
        for tool in mock_tool_data:
            txn.execute(
                """
                INSERT INTO tool_registry
                (tool_id, name, category, description, source_url, install_command, tags, confidence_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tool["tool_id"],
                    tool["name"],
                    tool["category"],
                    tool["description"],
                    tool["source_url"],
                    tool["install_command"],
                    tool["tags"],
                    tool["confidence_score"],
                ),
            )
    # Return wrapped connection that ignores close() calls
    return NonClosingConnection(conn)


# ── Tests ──────────────────────────────────────────────────────────────────


class TestBuildIndex:
    """Test suite for TF-IDF index building."""

    def test_build_index_success(self, in_memory_db):
        """Verify TF-IDF vectorizer builds successfully with test data."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            # Reset global state
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            vectorizer = tool_search.build_index()

            assert vectorizer is not None
            assert tool_search._tool_data is not None
            assert len(tool_search._tool_data) == 20
            assert tool_search._tfidf_matrix is not None

    def test_build_index_empty_database(self):
        """Verify build_index handles empty database gracefully."""
        # Create a fresh in-memory database for testing (isolated from shared connection)
        empty_conn = sqlite3.connect(":memory:")
        empty_conn.row_factory = sqlite3.Row
        empty_conn.execute("""
            CREATE TABLE tool_registry (
                tool_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT,
                description TEXT,
                source_url TEXT,
                install_command TEXT,
                tags TEXT,
                confidence_score REAL
            )
        """)

        with patch("control.research.tools.studio_db._connect", return_value=empty_conn):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            vectorizer = tool_search.build_index()

            assert vectorizer is not None
            assert tool_search._tool_data == []
            assert tool_search._tfidf_matrix is None

    def test_build_index_includes_tags_and_description(self, in_memory_db):
        """Verify corpus includes description, name, and tags."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            tool_search.build_index()

            # Verify corpus was built from combined text
            assert tool_search._tool_data is not None
            for tool in tool_search._tool_data:
                assert tool["name"]  # Name should be present
                assert tool["description"]  # Description should be present
                assert tool["tags"]  # Tags should be present


class TestSearchTools:
    """Test suite for tool search functionality."""

    def test_search_tools_video_processing(self, in_memory_db):
        """Query 'video processing' should return ffmpeg-python as top result."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("video processing", top_k=5)

            assert len(results) > 0
            assert any(r.name == "ffmpeg-python" for r in results)
            # ffmpeg-python should be highly ranked
            top_match = results[0]
            assert top_match.confidence >= 0.5

    def test_search_tools_machine_learning(self, in_memory_db):
        """Query 'machine learning' should return ML frameworks."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("machine learning", top_k=5)

            assert len(results) > 0
            ml_tools = {r.name for r in results}
            # Should include at least one ML framework
            assert any(name in ml_tools for name in ["TensorFlow", "PyTorch", "Scikit-learn"])

    def test_search_tools_empty_query(self, in_memory_db):
        """Empty query should return empty results."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("", top_k=5)

            assert results == []

    def test_search_tools_whitespace_only_query(self, in_memory_db):
        """Whitespace-only query should return empty results."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("   ", top_k=5)

            assert results == []

    def test_search_tools_no_matches(self, in_memory_db):
        """Query with no matches should return empty results."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("xyzabc123nonexistent", top_k=5)

            # Should return empty or very low confidence results
            assert len(results) == 0 or all(r.confidence < 0.5 for r in results)

    def test_search_tools_respects_top_k(self, in_memory_db):
        """Search should respect top_k parameter."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("database", top_k=3)

            assert len(results) <= 3

    def test_search_tools_filters_low_confidence(self, in_memory_db):
        """Search should filter out results with confidence < 0.5."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("web", top_k=10)

            assert all(r.confidence >= 0.5 for r in results)


class TestConfidenceScores:
    """Test suite for confidence score calculation."""

    def test_calculate_confidence_high_similarity(self):
        """High similarity (0.9) should yield high confidence."""
        confidence = tool_search.calculate_confidence(0.9, 1.0)

        assert confidence >= 0.7
        assert confidence <= 1.0
        # Expected: 0.7 * 0.9 + 0.3 * 1.0 = 0.63 + 0.3 = 0.93
        assert abs(confidence - 0.93) < 0.01

    def test_calculate_confidence_low_similarity(self):
        """Low similarity (0.3) should yield lower confidence."""
        confidence = tool_search.calculate_confidence(0.3, 1.0)

        assert confidence >= 0.0
        assert confidence <= 1.0
        # Expected: 0.7 * 0.3 + 0.3 * 1.0 = 0.21 + 0.3 = 0.51
        assert abs(confidence - 0.51) < 0.01

    def test_calculate_confidence_weights_similarity_and_registry(self):
        """Confidence should combine similarity (70%) and registry score (30%)."""
        similarity = 0.8
        registry_score = 0.6

        confidence = tool_search.calculate_confidence(similarity, registry_score)

        expected = 0.7 * 0.8 + 0.3 * 0.6
        assert abs(confidence - expected) < 0.01

    def test_calculate_confidence_rounds_to_three_decimals(self):
        """Confidence should round to 3 decimal places."""
        confidence = tool_search.calculate_confidence(0.7777, 0.8888)

        # Should be rounded to 3 decimals
        assert len(str(confidence).split(".")[-1]) <= 3

    def test_calculate_confidence_edge_case_zero(self):
        """Zero similarity and registry score should yield 0."""
        confidence = tool_search.calculate_confidence(0.0, 0.0)

        assert confidence == 0.0

    def test_calculate_confidence_edge_case_one(self):
        """Max similarity and registry score should yield 1.0."""
        confidence = tool_search.calculate_confidence(1.0, 1.0)

        assert confidence == 1.0


class TestFilterByCategory:
    """Test suite for category filtering."""

    def test_filter_by_category_mcp_only(self, in_memory_db):
        """Filter results to show only MCP servers."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("web", top_k=20)
            filtered = tool_search.filter_by_category(results, "mcp")

            assert all(r.category == "mcp" for r in filtered)

    def test_filter_by_category_python_package(self, in_memory_db):
        """Filter results to show only Python packages."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("python library", top_k=20)
            filtered = tool_search.filter_by_category(results, "python_package")

            assert all(r.category == "python_package" for r in filtered)

    def test_filter_by_category_empty_category(self, in_memory_db):
        """Empty category string should return all results."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("web", top_k=20)
            filtered = tool_search.filter_by_category(results, "")

            assert len(filtered) == len(results)

    def test_filter_by_category_no_matches(self, in_memory_db):
        """Filter with non-matching category should return empty list."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("web", top_k=20)
            filtered = tool_search.filter_by_category(results, "nonexistent_category")

            assert len(filtered) == 0

    def test_filter_by_category_preserves_order(self, in_memory_db):
        """Filtering should preserve result order."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("tool", top_k=20)
            if len(results) > 1:
                original_names = [r.name for r in results]
                filtered = tool_search.filter_by_category(results, "python_package")
                filtered_names = [r.name for r in filtered]

                # Filtered results should maintain relative order
                for i in range(len(filtered_names) - 1):
                    idx1 = original_names.index(filtered_names[i])
                    idx2 = original_names.index(filtered_names[i + 1])
                    assert idx1 < idx2


class TestSearchCache:
    """Test suite for search caching behavior."""

    def test_cache_hit_same_query(self, in_memory_db):
        """Running search twice should use cached index."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            # First search builds index
            results1 = tool_search.search_tools("database", top_k=5)
            vectorizer_id_1 = id(tool_search._vectorizer)

            # Second search should reuse cache
            results2 = tool_search.search_tools("database", top_k=5)
            vectorizer_id_2 = id(tool_search._vectorizer)

            # Same vectorizer instance should be used
            assert vectorizer_id_1 == vectorizer_id_2
            assert results1 == results2

    def test_cache_miss_after_rebuild(self, in_memory_db):
        """rebuild_index() should clear cache and create new index."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            # Build initial index
            tool_search.search_tools("web", top_k=5)
            vectorizer_id_1 = id(tool_search._vectorizer)

            # Rebuild index
            success = tool_search.rebuild_index()

            assert success is True
            vectorizer_id_2 = id(tool_search._vectorizer)
            # Should be a new vectorizer instance
            assert vectorizer_id_1 != vectorizer_id_2

    def test_rebuild_index_success(self, in_memory_db):
        """rebuild_index should return True on success."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            success = tool_search.rebuild_index()

            assert success is True
            assert tool_search._vectorizer is not None

    def test_rebuild_index_clears_globals(self, in_memory_db):
        """rebuild_index should reset global state before rebuilding."""
        with patch("control.research.tools.studio_db._connect", return_value=in_memory_db):
            # Set initial state
            tool_search._vectorizer = "dummy"
            tool_search._tfidf_matrix = "dummy"
            tool_search._tool_data = "dummy"

            # Rebuild
            tool_search.rebuild_index()

            # State should be repopulated (not None or dummy)
            assert tool_search._vectorizer is not None
            assert tool_search._vectorizer != "dummy"
            assert tool_search._tfidf_matrix is not None
            assert tool_search._tool_data is not None
            assert tool_search._tool_data != "dummy"


class TestToolMatchDataclass:
    """Test suite for ToolMatch dataclass."""

    def test_tool_match_creation(self):
        """Verify ToolMatch can be created with all fields."""
        match = tool_search.ToolMatch(
            tool_id="1",
            name="ffmpeg-python",
            category="python_package",
            description="Video processing library",
            confidence=0.95,
            source_url="https://github.com/kkroening/ffmpeg-python",
            install_command="pip install ffmpeg-python",
        )

        assert match.tool_id == "1"
        assert match.name == "ffmpeg-python"
        assert match.category == "python_package"
        assert match.confidence == 0.95
        assert isinstance(match, tool_search.ToolMatch)


# ── Semantic Search Tests (T148) ──────────────────────────────────────────


class TestEmbeddingIndex:
    """Test suite for semantic search embedding index building and caching."""

    def test_embedding_index(self, in_memory_db, mock_tool_data):
        """Verify embeddings are built and cached correctly in SQLite."""
        # Create mock sentence-transformers model
        mock_model = MagicMock()
        # Create deterministic embeddings (384-dim for all-MiniLM-L6-v2)
        # Each tool gets a unique but predictable embedding
        mock_embeddings = []
        for i in range(len(mock_tool_data)):
            # Create embedding with values based on tool_id for determinism
            embedding = (
                np.random.RandomState(seed=int(mock_tool_data[i]["tool_id"]))
                .randn(384)
                .astype(np.float32)
            )
            mock_embeddings.append(embedding)

        mock_model.encode.return_value = np.array(mock_embeddings)

        # Mock _connect to always return the same in-memory connection (don't actually close it)
        with patch("control.research.tools.studio_db._connect") as mock_connect:
            mock_connect.return_value = in_memory_db
            # Mock close to be a no-op so we can reuse the connection

            with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
                # Reset global state
                tool_search._sentence_model = None
                tool_search._embeddings_matrix = None
                tool_search._embedding_tool_ids = None
                tool_search._tool_data = None

                # Build embedding index
                model = tool_search.build_embedding_index()

                # Verify model was loaded
                assert model is not None
                assert tool_search._sentence_model == mock_model

                # Verify embeddings matrix was created
                assert tool_search._embeddings_matrix is not None
                assert tool_search._embeddings_matrix.shape == (len(mock_tool_data), 384)

                # Verify tool IDs were cached
                assert tool_search._embedding_tool_ids is not None
                assert len(tool_search._embedding_tool_ids) == len(mock_tool_data)

                # Verify embeddings were saved to database
                cached = in_memory_db.execute("""
                    SELECT tool_id, embedding, model_name
                    FROM tool_embeddings_cache
                """).fetchall()

                assert len(cached) == len(mock_tool_data)
                for row in cached:
                    assert row["model_name"] == tool_search.EMBEDDING_MODEL
                    assert row["embedding"] is not None
                    # Verify embedding can be deserialized
                    embedding = np.frombuffer(row["embedding"], dtype=np.float32)
                    assert embedding.shape == (384,)

    def test_embedding_cache_reuse(self, in_memory_db, mock_tool_data):
        """Verify cached embeddings are reused on subsequent builds."""
        # Pre-populate cache with embeddings
        mock_model = MagicMock()

        # Create and cache embeddings for first 10 tools using transaction pattern
        with _test_db_transaction(in_memory_db) as txn:
            for i in range(10):
                tool_id = mock_tool_data[i]["tool_id"]
                embedding = np.random.RandomState(seed=int(tool_id)).randn(384).astype(np.float32)
                embedding_bytes = embedding.tobytes()

                txn.execute(
                    """
                    INSERT INTO tool_embeddings_cache (tool_id, embedding, model_name)
                    VALUES (?, ?, ?)
                """,
                    (tool_id, embedding_bytes, tool_search.EMBEDDING_MODEL),
                )

        # Mock encode to return embeddings for remaining 10 tools only
        remaining_embeddings = []
        for i in range(10, len(mock_tool_data)):
            tool_id = mock_tool_data[i]["tool_id"]
            embedding = np.random.RandomState(seed=int(tool_id)).randn(384).astype(np.float32)
            remaining_embeddings.append(embedding)

        mock_model.encode.return_value = np.array(remaining_embeddings)

        # Mock _connect to always return the same in-memory connection
        with patch("control.research.tools.studio_db._connect") as mock_connect:
            mock_connect.return_value = in_memory_db

            with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
                # Reset global state
                tool_search._sentence_model = None
                tool_search._embeddings_matrix = None
                tool_search._embedding_tool_ids = None
                tool_search._tool_data = None

                # Build embedding index
                tool_search.build_embedding_index()

                # Verify encode was called only for non-cached tools (10 tools)
                assert mock_model.encode.call_count == 1
                encoded_corpus = mock_model.encode.call_args[0][0]
                assert len(encoded_corpus) == 10  # Only 10 new tools needed encoding

                # Verify all 20 embeddings are in the matrix
                assert tool_search._embeddings_matrix.shape == (20, 384)

                # Verify database now has all 20 cached embeddings
                cached = in_memory_db.execute("""
                    SELECT COUNT(*) as count FROM tool_embeddings_cache
                """).fetchone()
                assert cached["count"] == 20


class TestSemanticSearch:
    """Test suite for semantic search with sentence-transformers."""

    def test_semantic_search(self, in_memory_db, mock_tool_data):
        """Verify 'process videos' matches ffmpeg-python with semantic search."""
        # Create mock model and embeddings
        mock_model = MagicMock()

        # Create embeddings where ffmpeg-python (tool_id=1) is semantically close to "process videos"
        # For "process videos" query, create embedding [1.0, 0.9, 0.8, ...]
        query_embedding = np.array([1.0, 0.9, 0.8] + [0.1] * 381, dtype=np.float32)

        # ffmpeg-python embedding: very similar to query (high cosine similarity)
        ffmpeg_embedding = np.array([0.95, 0.88, 0.82] + [0.12] * 381, dtype=np.float32)

        # Other tools: less similar embeddings
        tool_embeddings = []
        for i, tool in enumerate(mock_tool_data):
            if tool["tool_id"] == "1":  # ffmpeg-python
                tool_embeddings.append(ffmpeg_embedding)
            else:
                # Create random but different embeddings
                embedding = np.random.RandomState(seed=100 + i).randn(384).astype(np.float32)
                tool_embeddings.append(embedding)

        # Mock encode to return query embedding for queries, tool embeddings for corpus
        def encode_side_effect(texts, show_progress_bar=False):
            if isinstance(texts, list) and len(texts) == 1:
                # Query encoding
                return np.array([query_embedding])
            else:
                # Corpus encoding
                return np.array(tool_embeddings)

        mock_model.encode.side_effect = encode_side_effect

        with patch("control.research.tools.studio_db._connect") as mock_connect:
            mock_connect.return_value = in_memory_db
            with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
                # Reset global state
                tool_search._sentence_model = None
                tool_search._embeddings_matrix = None
                tool_search._embedding_tool_ids = None
                tool_search._tool_data = None

                # Perform semantic search
                results = tool_search.search_tools("process videos", top_k=5, use_embeddings=True)

                # Verify ffmpeg-python is in results (should be top result due to high similarity)
                assert len(results) > 0
                tool_names = [r.name for r in results]
                assert "ffmpeg-python" in tool_names

                # Verify ffmpeg-python has high confidence
                ffmpeg_match = next(r for r in results if r.name == "ffmpeg-python")
                assert ffmpeg_match.confidence >= 0.7

                # Verify results are sorted by confidence
                confidences = [r.confidence for r in results]
                assert confidences == sorted(confidences, reverse=True)

    def test_semantic_search_fallback_to_tfidf(self, in_memory_db):
        """Verify semantic search falls back to TF-IDF if sentence-transformers fails."""
        # Mock SentenceTransformer to raise ImportError
        with patch("control.research.tools.studio_db._connect") as mock_connect:
            mock_connect.return_value = in_memory_db
            with patch(
                "sentence_transformers.SentenceTransformer",
                side_effect=ImportError("Model not found"),
            ):
                # Reset global state
                tool_search._vectorizer = None
                tool_search._tfidf_matrix = None
                tool_search._tool_data = None
                tool_search._sentence_model = None
                tool_search._embeddings_matrix = None
                tool_search._embedding_tool_ids = None

                # Attempt semantic search
                results = tool_search.search_tools("video processing", top_k=5, use_embeddings=True)

                # Should still return results via TF-IDF fallback
                assert len(results) > 0
                # Should include video-related tools
                assert any(r.name in ["ffmpeg-python", "OpenCV"] for r in results)


class TestHybridSearch:
    """Test suite for hybrid search (TF-IDF + embeddings combined scoring)."""

    def test_hybrid_search(self, in_memory_db, mock_tool_data):
        """Verify hybrid search combines TF-IDF and embedding scores correctly."""
        # Create mock model and embeddings
        mock_model = MagicMock()

        # Query: "web framework"
        query_embedding = np.array([1.0, 0.9, 0.8] + [0.1] * 381, dtype=np.float32)

        # Django (tool_id=9): high semantic similarity to "web framework"
        django_embedding = np.array([0.98, 0.91, 0.79] + [0.11] * 381, dtype=np.float32)

        # Flask (tool_id=10): medium semantic similarity
        flask_embedding = np.array([0.85, 0.80, 0.75] + [0.15] * 381, dtype=np.float32)

        # Other tools: lower similarity
        tool_embeddings = []
        for i, tool in enumerate(mock_tool_data):
            if tool["tool_id"] == "9":  # Django
                tool_embeddings.append(django_embedding)
            elif tool["tool_id"] == "10":  # Flask
                tool_embeddings.append(flask_embedding)
            else:
                embedding = np.random.RandomState(seed=200 + i).randn(384).astype(np.float32)
                tool_embeddings.append(embedding)

        def encode_side_effect(texts, show_progress_bar=False):
            if isinstance(texts, list) and len(texts) == 1:
                return np.array([query_embedding])
            else:
                return np.array(tool_embeddings)

        mock_model.encode.side_effect = encode_side_effect

        with patch("control.research.tools.studio_db._connect") as mock_connect:
            mock_connect.return_value = in_memory_db
            with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
                # Reset global state
                tool_search._vectorizer = None
                tool_search._tfidf_matrix = None
                tool_search._tool_data = None
                tool_search._sentence_model = None
                tool_search._embeddings_matrix = None
                tool_search._embedding_tool_ids = None
                tool_search._query_cache.clear()

                # Perform hybrid search
                results = tool_search.hybrid_search("web framework", top_k=5)

                # Verify results exist
                assert len(results) > 0

                # Verify web frameworks are highly ranked
                tool_names = [r.name for r in results]
                assert any(name in tool_names for name in ["Django", "Flask"])

                # Verify confidence scores are in valid range
                for result in results:
                    assert 0.0 <= result.confidence <= 1.0

                # Verify results are sorted by confidence
                confidences = [r.confidence for r in results]
                assert confidences == sorted(confidences, reverse=True)

                # Verify hybrid scoring combines both methods
                # Top result should have high confidence from both TF-IDF and embeddings
                if results:
                    top_result = results[0]
                    assert top_result.confidence >= 0.3  # Minimum threshold for hybrid

    def test_hybrid_search_respects_category_filter(self, in_memory_db, mock_tool_data):
        """Verify hybrid search respects category parameter."""
        mock_model = MagicMock()

        # Create simple embeddings
        query_embedding = np.random.randn(384).astype(np.float32)
        tool_embeddings = [np.random.randn(384).astype(np.float32) for _ in mock_tool_data]

        def encode_side_effect(texts, show_progress_bar=False):
            if isinstance(texts, list) and len(texts) == 1:
                return np.array([query_embedding])
            else:
                return np.array(tool_embeddings)

        mock_model.encode.side_effect = encode_side_effect

        with patch("control.research.tools.studio_db._connect") as mock_connect:
            mock_connect.return_value = in_memory_db
            with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
                # Reset global state
                tool_search._vectorizer = None
                tool_search._tfidf_matrix = None
                tool_search._tool_data = None
                tool_search._sentence_model = None
                tool_search._embeddings_matrix = None
                tool_search._embedding_tool_ids = None
                tool_search._query_cache.clear()

                # Search with category filter
                results = tool_search.hybrid_search("web", top_k=10, category="mcp")

                # Verify all results are from MCP category
                assert all(r.category == "mcp" for r in results)

    def test_hybrid_search_caching(self, in_memory_db, mock_tool_data):
        """Verify hybrid search results are cached correctly."""
        mock_model = MagicMock()

        query_embedding = np.random.randn(384).astype(np.float32)
        tool_embeddings = [np.random.randn(384).astype(np.float32) for _ in mock_tool_data]

        def encode_side_effect(texts, show_progress_bar=False):
            if isinstance(texts, list) and len(texts) == 1:
                return np.array([query_embedding])
            else:
                return np.array(tool_embeddings)

        mock_model.encode.side_effect = encode_side_effect

        with patch("control.research.tools.studio_db._connect") as mock_connect:
            mock_connect.return_value = in_memory_db
            with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
                # Reset global state
                tool_search._vectorizer = None
                tool_search._tfidf_matrix = None
                tool_search._tool_data = None
                tool_search._sentence_model = None
                tool_search._embeddings_matrix = None
                tool_search._embedding_tool_ids = None
                tool_search._query_cache.clear()

                # First search
                results1 = tool_search.hybrid_search("database", top_k=5)

                # Get cache stats
                stats_after_first = tool_search.get_cache_stats()
                first_misses = stats_after_first["misses"]

                # Second search (same query)
                results2 = tool_search.hybrid_search("database", top_k=5)

                # Get cache stats again
                stats_after_second = tool_search.get_cache_stats()

                # Verify cache was hit (misses didn't increase)
                assert stats_after_second["misses"] == first_misses
                assert stats_after_second["hits"] > stats_after_first["hits"]

                # Verify results are identical
                assert len(results1) == len(results2)
                for r1, r2 in zip(results1, results2):
                    assert r1.tool_id == r2.tool_id
                    assert r1.confidence == r2.confidence
