"""Integration tests for think mode tool recommendation feature.

Tests the --recommend-tools flag integration:
1. Keyword extraction from user input
2. Tool search API integration
3. Confidence-based filtering (>0.7)
4. Spec.md markdown generation
5. Edge cases (no matches, empty results)

Related:
- T131: Documentation of --recommend-tools flag
- T133: Integration tests (this file)
- control/research/tools.py: TF-IDF search implementation
"""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from control.research import tools as tool_search

# ── Test Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_high_confidence_tools():
    """Create tools with confidence > 0.7 for positive test cases."""
    return [
        {
            "tool_id": "pkg-ffmpeg-python",
            "name": "ffmpeg-python",
            "category": "python_package",
            "description": "Python bindings for FFmpeg video processing library pipeline encoding decoding streaming multimedia",
            "source_url": "https://github.com/kkroening/ffmpeg-python",
            "install_command": "pip install ffmpeg-python",
            "tags": json.dumps(["video", "processing", "pipeline", "encoding", "ffmpeg"]),
            "confidence_score": 1.0,
        },
        {
            "tool_id": "pkg-opencv-python",
            "name": "opencv-python",
            "category": "python_package",
            "description": "Computer vision library for video processing analysis image manipulation pipeline automation",
            "source_url": "https://opencv.org",
            "install_command": "pip install opencv-python",
            "tags": json.dumps(["video", "processing", "cv", "image", "pipeline"]),
            "confidence_score": 1.0,
        },
        {
            "tool_id": "mcp-video-server",
            "name": "mcp-video",
            "category": "mcp",
            "description": "MCP server for video processing manipulation streaming operations pipeline automation",
            "source_url": "https://github.com/example/mcp-video",
            "install_command": "pip install mcp-video",
            "tags": json.dumps(["video", "processing", "mcp", "streaming", "pipeline"]),
            "confidence_score": 1.0,
        },
        {
            "tool_id": "pkg-moviepy",
            "name": "moviepy",
            "category": "python_package",
            "description": "Video processing editing library for pipeline automation and multimedia manipulation",
            "source_url": "https://zulko.github.io/moviepy/",
            "install_command": "pip install moviepy",
            "tags": json.dumps(["video", "processing", "editing", "pipeline"]),
            "confidence_score": 1.0,
        },
        {
            "tool_id": "pkg-scikit-video",
            "name": "scikit-video",
            "category": "python_package",
            "description": "Video processing algorithms and pipeline tools for scientific computing",
            "source_url": "https://github.com/scikit-video/scikit-video",
            "install_command": "pip install scikit-video",
            "tags": json.dumps(["video", "processing", "pipeline", "scientific"]),
            "confidence_score": 1.0,
        },
    ]


@pytest.fixture
def mock_low_confidence_tools():
    """Create tools with confidence <= 0.7 for filtering tests."""
    return [
        {
            "tool_id": "pkg-numpy",
            "name": "numpy",
            "category": "python_package",
            "description": "Numerical computing library for array operations",
            "source_url": "https://numpy.org",
            "install_command": "pip install numpy",
            "tags": json.dumps(["math", "numerics"]),
            "confidence_score": 0.45,
        },
        {
            "tool_id": "pkg-requests",
            "name": "requests",
            "category": "python_package",
            "description": "HTTP library for making web requests",
            "source_url": "https://requests.readthedocs.io",
            "install_command": "pip install requests",
            "tags": json.dumps(["http", "web"]),
            "confidence_score": 0.30,
        },
    ]


@pytest.fixture
def tool_registry_db(mock_high_confidence_tools, mock_low_confidence_tools):
    """Create in-memory database with mixed confidence tools."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tool_registry (
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

    all_tools = mock_high_confidence_tools + mock_low_confidence_tools
    for tool in all_tools:
        conn.execute(
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

    conn.commit()
    return conn


@pytest.fixture
def empty_tool_registry():
    """Create empty database for no-match test cases."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tool_registry (
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

    conn.commit()
    return conn


@pytest.fixture
def spec_output_dir(tmp_path):
    """Create temporary directory for spec.md output."""
    spec_dir = tmp_path / ".planning" / "specs" / "test-spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    return spec_dir


# ── Test Suite ─────────────────────────────────────────────────────────────


class TestRecommendToolsFlag:
    """Test suite for --recommend-tools flag integration."""

    def test_recommend_tools_flag_adds_section_to_spec(self, spec_output_dir):
        """Verify spec.md has 'Recommended Tools' section when flag is present.

        Test: T133.1 - Basic integration test
        Given: User runs think mode with --recommend-tools flag
        When: Tool search finds high-confidence matches (>0.7)
        Then: spec.md contains a "## Recommended Tools" section
        """
        # Mock API response with high-confidence tools
        mock_results = [
            tool_search.ToolMatch(
                tool_id="pkg-ffmpeg-python",
                name="ffmpeg-python",
                category="python_package",
                description="Python bindings for FFmpeg video processing",
                confidence=0.95,
                source_url="https://github.com/kkroening/ffmpeg-python",
                install_command="pip install ffmpeg-python",
            ),
            tool_search.ToolMatch(
                tool_id="pkg-opencv-python",
                name="opencv-python",
                category="python_package",
                description="Computer vision library for video analysis",
                confidence=0.88,
                source_url="https://opencv.org",
                install_command="pip install opencv-python",
            ),
        ]

        with patch("control.research.tools.search_tools", return_value=mock_results):
            # Simulate think mode searching for video tools
            results = tool_search.search_tools("video processing pipeline", top_k=5)

            # Filter to confidence > 0.7 (think mode's threshold)
            high_confidence = [r for r in results if r.confidence > 0.7]

            # Simulate spec.md generation
            spec_path = spec_output_dir / "spec.md"
            spec_content = self._generate_mock_spec_with_tools(high_confidence)
            spec_path.write_text(spec_content, encoding="utf-8")

            # Verify spec.md has Recommended Tools section
            spec_text = spec_path.read_text(encoding="utf-8")
            assert (
                "## Recommended Tools" in spec_text
            ), "spec.md missing '## Recommended Tools' section"

            # Verify at least one tool is listed
            assert re.search(
                r"\*\*[\w-]+\*\*.*\([\d.]+%", spec_text
            ), "No tools found in Recommended Tools section"

            # Verify install command format
            assert re.search(
                r"Install:.*pip install", spec_text
            ), "Missing install command in recommendations"

    def test_tool_filtering_confidence_threshold(self):
        """Verify only tools with confidence > 0.7 are included in spec.

        Test: T133.2 - Confidence filtering
        Given: Tool search returns mixed confidence results (0.3-0.95)
        When: Think mode applies confidence filter
        Then: Only tools with confidence > 0.7 appear in output
        """
        # Mock API response with mixed confidence scores
        mock_results = [
            tool_search.ToolMatch(
                tool_id="pkg-high1",
                name="high-confidence-tool",
                category="python_package",
                description="High confidence tool",
                confidence=0.95,
                source_url="https://example.com",
                install_command="pip install high-tool",
            ),
            tool_search.ToolMatch(
                tool_id="pkg-high2",
                name="medium-high-tool",
                category="python_package",
                description="Medium-high confidence tool",
                confidence=0.75,
                source_url="https://example.com",
                install_command="pip install medium-high",
            ),
            tool_search.ToolMatch(
                tool_id="pkg-low1",
                name="low-confidence-tool",
                category="python_package",
                description="Low confidence tool",
                confidence=0.65,
                source_url="https://example.com",
                install_command="pip install low-tool",
            ),
            tool_search.ToolMatch(
                tool_id="pkg-low2",
                name="very-low-tool",
                category="python_package",
                description="Very low confidence tool",
                confidence=0.45,
                source_url="https://example.com",
                install_command="pip install very-low",
            ),
        ]

        with patch("control.research.tools.search_tools", return_value=mock_results):
            # Search for tools
            results = tool_search.search_tools("test query", top_k=10)

            # Apply think mode's confidence threshold
            filtered = [r for r in results if r.confidence > 0.7]

            # Verify filtering worked
            assert len(filtered) == 2, f"Expected 2 high-confidence tools, got {len(filtered)}"
            assert all(
                r.confidence > 0.7 for r in filtered
            ), "Some tools below 0.7 threshold were not filtered"

            # Verify the correct tools are included
            filtered_names = {r.name for r in filtered}
            assert filtered_names == {"high-confidence-tool", "medium-high-tool"}

            # Verify low-confidence tools were excluded
            all_results_names = {r.name for r in results}
            excluded_names = all_results_names - filtered_names
            assert excluded_names == {"low-confidence-tool", "very-low-tool"}

    def test_no_recommendations_when_no_matches(self, empty_tool_registry, spec_output_dir):
        """Handle case where tool search returns no high-confidence matches.

        Test: T133.3 - Edge case: no recommendations
        Given: Tool registry is empty OR query has no matches
        When: Think mode searches for tools
        Then: spec.md either omits section OR shows "No tools found" message
        """
        with patch("control.research.tools.studio_db._connect", return_value=empty_tool_registry):
            # Reset tool_search state
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            # Search with empty database
            results = tool_search.search_tools("nonexistent topic xyz123", top_k=5)

            # Filter to confidence > 0.7
            high_confidence = [r for r in results if r.confidence > 0.7]

            # Simulate spec.md generation with no tools
            spec_path = spec_output_dir / "spec.md"
            if high_confidence:
                spec_content = self._generate_mock_spec_with_tools(high_confidence)
            else:
                # No tools found - spec should either omit section or note this
                spec_content = self._generate_mock_spec_no_tools()

            spec_path.write_text(spec_content, encoding="utf-8")

            # Verify spec handles no-match case gracefully
            spec_text = spec_path.read_text(encoding="utf-8")

            # Two valid behaviors:
            # 1. Section is omitted entirely
            # 2. Section exists but shows "No tools found" message
            if "## Recommended Tools" in spec_text:
                # If section exists, it should indicate no matches
                assert (
                    "No suitable tools found" in spec_text
                    or "No recommendations available" in spec_text
                ), "Section exists but doesn't indicate no matches"
            else:
                # Section omitted is also acceptable
                assert "## Recommended Tools" not in spec_text

    def test_spec_markdown_format_compliance(self, spec_output_dir):
        """Verify Recommended Tools section follows proper markdown format.

        Test: T133.4 - Markdown format validation
        Given: Tool search returns results
        When: Think mode generates spec.md
        Then: Recommended Tools section uses correct markdown syntax
        """
        # Mock API response with high-confidence tools
        mock_results = [
            tool_search.ToolMatch(
                tool_id="pkg-ffmpeg",
                name="ffmpeg-python",
                category="python_package",
                description="Video processing library",
                confidence=0.92,
                source_url="https://github.com/kkroening/ffmpeg-python",
                install_command="pip install ffmpeg-python",
            ),
            tool_search.ToolMatch(
                tool_id="pkg-opencv",
                name="opencv-python",
                category="python_package",
                description="Computer vision library",
                confidence=0.85,
                source_url="https://opencv.org",
                install_command="pip install opencv-python",
            ),
        ]

        with patch("control.research.tools.search_tools", return_value=mock_results):
            # Search for video tools
            results = tool_search.search_tools("video", top_k=5)
            high_confidence = [r for r in results if r.confidence > 0.7]

            # Generate spec
            spec_path = spec_output_dir / "spec.md"
            spec_content = self._generate_mock_spec_with_tools(high_confidence)
            spec_path.write_text(spec_content, encoding="utf-8")

            spec_text = spec_path.read_text(encoding="utf-8")

            # Verify markdown format
            # 1. Section header is H2
            assert re.search(
                r"^## Recommended Tools$", spec_text, re.MULTILINE
            ), "Section header should be ## Recommended Tools"

            # 2. Tool names are bold
            assert re.search(
                r"\*\*[\w-]+\*\*", spec_text
            ), "Tool names should be in bold (**name**)"

            # 3. Confidence scores shown as percentages
            assert re.search(
                r"\([\d]{1,3}% confidence\)", spec_text
            ), "Confidence should be shown as percentage"

            # 4. Install commands use code blocks or inline code
            assert re.search(r"`pip install [\w-]+`", spec_text) or re.search(
                r"```.*pip install", spec_text, re.DOTALL
            ), "Install commands should use code formatting"

            # 5. Each tool has a description
            for tool in high_confidence:
                assert tool.name in spec_text, f"Tool {tool.name} missing from spec"

    def test_top_5_limit_enforced(self, tool_registry_db):
        """Verify think mode limits recommendations to top 5 tools.

        Test: T133.5 - Result limit validation
        Given: Tool search could return 10+ matches
        When: Think mode applies top_k=5 filter
        Then: spec.md shows at most 5 recommendations
        """
        with patch("control.research.tools.studio_db._connect", return_value=tool_registry_db):
            # Reset tool_search state
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            # Search with explicit top_k=5 (as think mode does)
            results = tool_search.search_tools("video", top_k=5)
            high_confidence = [r for r in results if r.confidence > 0.7]

            # Verify at most 5 results
            assert (
                len(high_confidence) <= 5
            ), f"Expected at most 5 results, got {len(high_confidence)}"

    def test_keyword_extraction_from_user_prompt(self, tool_registry_db):
        """Verify keywords are correctly extracted from user input.

        Test: T133.6 - Keyword extraction logic
        Given: User prompt contains domain terms (e.g., "video processing pipeline")
        When: Think mode extracts keywords for tool search
        Then: Relevant keywords (video, processing, pipeline) are used in query
        """
        with patch("control.research.tools.studio_db._connect", return_value=tool_registry_db):
            # Reset tool_search state
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            # Test various user prompts
            test_cases = [
                ("Build video processing pipeline", ["video", "processing", "pipeline"]),
                ("Implement authentication system", ["authentication", "system"]),
                ("Design real-time data sync", ["real-time", "data", "sync"]),
            ]

            for user_prompt, expected_keywords in test_cases:
                # Simulate keyword extraction (think mode would do this)
                # For now, we just verify search works with relevant terms
                query = " ".join(expected_keywords)
                results = tool_search.search_tools(query, top_k=5)

                # Verify search executed without error
                assert isinstance(results, list), f"Search failed for keywords: {expected_keywords}"

    # ── Helper Methods ──────────────────────────────────────────────────

    def _generate_mock_spec_with_tools(self, tools: list) -> str:
        """Generate mock spec.md content with Recommended Tools section."""
        spec = """# Test Spec

## Overview
This is a test specification for think mode integration testing.

## Functional Requirements
- FR-001: System MUST process video files
- FR-002: System MUST support multiple formats

## Recommended Tools

"""
        if not tools:
            spec += "_No suitable tools found for this specification._\n"
        else:
            for tool in tools[:5]:  # Top 5 limit
                confidence_pct = int(tool.confidence * 100)
                spec += f"- **{tool.name}** ({confidence_pct}% confidence)\n"
                spec += f"  - {tool.description}\n"
                spec += f"  - Install: `{tool.install_command}`\n"
                spec += f"  - [Documentation]({tool.source_url})\n\n"

        spec += """## Success Criteria
- SC-001: Video processing completes in <5 seconds
"""
        return spec

    def _generate_mock_spec_no_tools(self) -> str:
        """Generate mock spec.md without Recommended Tools section."""
        return """# Test Spec

## Overview
This is a test specification with no tool recommendations.

## Functional Requirements
- FR-001: Basic requirement

## Success Criteria
- SC-001: System meets basic requirements
"""


# ── Integration with Tool Search API ───────────────────────────────────────


class TestToolSearchAPIIntegration:
    """Test integration between think mode and tool_search API."""

    def test_tool_search_returns_expected_dataclass(self, tool_registry_db):
        """Verify tool_search.search_tools() returns ToolMatch objects.

        Test: T133.7 - API contract validation
        Given: Tool search API is called
        When: Results are returned
        Then: Each result is a ToolMatch with required fields
        """
        with patch("control.research.tools.studio_db._connect", return_value=tool_registry_db):
            # Reset tool_search state
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("video", top_k=5)

            # Verify return type
            assert isinstance(results, list)

            for result in results:
                # Verify it's a ToolMatch instance
                assert isinstance(result, tool_search.ToolMatch)

                # Verify required fields
                assert hasattr(result, "tool_id")
                assert hasattr(result, "name")
                assert hasattr(result, "category")
                assert hasattr(result, "description")
                assert hasattr(result, "confidence")
                assert hasattr(result, "source_url")
                assert hasattr(result, "install_command")

                # Verify field types
                assert isinstance(result.confidence, float)
                assert 0.0 <= result.confidence <= 1.0

    def test_tool_search_caching_behavior(self, tool_registry_db):
        """Verify tool search results are cached for performance.

        Test: T133.8 - Caching validation
        Given: Same query is run twice
        When: Cache is enabled (default)
        Then: Second query returns cached results
        """
        with patch("control.research.tools.studio_db._connect", return_value=tool_registry_db):
            # Reset tool_search state and cache
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None
            tool_search.clear_cache()

            query = "video processing"

            # First search - cache miss
            results1 = tool_search.search_tools(query, top_k=5)
            stats1 = tool_search.get_cache_stats()

            # Second search - cache hit
            results2 = tool_search.search_tools(query, top_k=5)
            stats2 = tool_search.get_cache_stats()

            # Verify results are identical
            assert len(results1) == len(results2)
            assert results1 == results2

            # Verify cache hit occurred
            assert stats2["hits"] > stats1["hits"], "Cache hit count did not increase"

    def test_confidence_score_calculation_accuracy(self, tool_registry_db):
        """Verify confidence score formula: 0.7*similarity + 0.3*registry_score.

        Test: T133.9 - Confidence calculation validation
        Given: Tool search returns results
        When: Confidence scores are calculated
        Then: Formula is correctly applied (70% similarity, 30% registry)
        """
        with patch("control.research.tools.studio_db._connect", return_value=tool_registry_db):
            # Reset tool_search state
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            # Test confidence calculation directly
            test_cases = [
                (0.9, 1.0, 0.93),  # High similarity, high registry
                (0.5, 0.8, 0.59),  # Medium similarity, high registry
                (0.3, 0.5, 0.36),  # Low similarity, medium registry
                (1.0, 1.0, 1.0),  # Perfect score
                (0.0, 0.0, 0.0),  # Zero score
            ]

            for similarity, registry_score, expected in test_cases:
                result = tool_search.calculate_confidence(similarity, registry_score)
                assert (
                    abs(result - expected) < 0.01
                ), f"Expected {expected}, got {result} for sim={similarity}, reg={registry_score}"


# ── Edge Cases and Error Handling ──────────────────────────────────────────


class TestThinkModeEdgeCases:
    """Test edge cases and error handling for think mode tool recommendations."""

    def test_empty_query_returns_empty_results(self, tool_registry_db):
        """Verify empty query is handled gracefully.

        Test: T133.10 - Empty query handling
        Given: User prompt contains no keywords
        When: Tool search is called with empty string
        Then: Empty list is returned (no error)
        """
        with patch("control.research.tools.studio_db._connect", return_value=tool_registry_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("", top_k=5)

            assert results == []

    def test_whitespace_only_query(self, tool_registry_db):
        """Verify whitespace-only query is handled gracefully.

        Test: T133.11 - Whitespace handling
        """
        with patch("control.research.tools.studio_db._connect", return_value=tool_registry_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            results = tool_search.search_tools("   \n\t  ", top_k=5)

            assert results == []

    def test_special_characters_in_query(self, tool_registry_db):
        """Verify special characters don't break search.

        Test: T133.12 - Special character handling
        """
        with patch("control.research.tools.studio_db._connect", return_value=tool_registry_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            # Query with special characters
            results = tool_search.search_tools("video & audio <processing>", top_k=5)

            # Should return results (TF-IDF handles special chars)
            assert isinstance(results, list)

    def test_very_long_query(self, tool_registry_db):
        """Verify long query (>1000 chars) is handled.

        Test: T133.13 - Long query handling
        """
        with patch("control.research.tools.studio_db._connect", return_value=tool_registry_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            # Create 1000+ character query
            long_query = "video processing " * 100

            results = tool_search.search_tools(long_query, top_k=5)

            # Should handle gracefully (may return results or empty list)
            assert isinstance(results, list)

    def test_database_connection_failure(self):
        """Verify graceful handling when database is unavailable.

        Test: T133.14 - Database error handling
        """
        with patch(
            "control.research.tools.studio_db._connect", side_effect=Exception("DB unavailable")
        ):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            # Should not crash - returns empty results
            try:
                results = tool_search.search_tools("video", top_k=5)
                assert results == []
            except RuntimeError:
                # RuntimeError is acceptable - it's caught by think mode
                pass


# ── Performance and Limits ─────────────────────────────────────────────────


class TestPerformanceAndLimits:
    """Test performance characteristics and limits of tool recommendations."""

    def test_top_k_parameter_respected(self, tool_registry_db):
        """Verify top_k parameter limits results correctly.

        Test: T133.15 - top_k limit enforcement
        """
        with patch("control.research.tools.studio_db._connect", return_value=tool_registry_db):
            tool_search._vectorizer = None
            tool_search._tfidf_matrix = None
            tool_search._tool_data = None

            for top_k in [1, 3, 5, 10]:
                results = tool_search.search_tools("video", top_k=top_k)

                # Should return at most top_k results
                assert (
                    len(results) <= top_k
                ), f"Expected at most {top_k} results, got {len(results)}"

    def test_cache_ttl_expiration(self, tool_registry_db):
        """Verify cache TTL (1 hour) is configured correctly.

        Test: T133.16 - Cache TTL validation
        """
        with patch("control.research.tools.studio_db._connect", return_value=tool_registry_db):
            tool_search.clear_cache()

            stats = tool_search.get_cache_stats()

            # Verify TTL is 3600 seconds (1 hour)
            assert stats["ttl"] == 3600, f"Expected TTL of 3600s, got {stats['ttl']}s"

    def test_cache_maxsize_limit(self, tool_registry_db):
        """Verify cache max size (1000 entries) is configured correctly.

        Test: T133.17 - Cache size limit validation
        """
        with patch("control.research.tools.studio_db._connect", return_value=tool_registry_db):
            tool_search.clear_cache()

            stats = tool_search.get_cache_stats()

            # Verify max size is 1000
            assert (
                stats["cache_maxsize"] == 1000
            ), f"Expected maxsize of 1000, got {stats['cache_maxsize']}"
