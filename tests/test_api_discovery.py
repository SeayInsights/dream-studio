"""API integration tests for unified-discovery Phase 5.3 API Layer.

Test suite covers the dependency graph endpoint:
1. test_graph_endpoint() - Verify nodes/edges JSON structure
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import patch, MagicMock

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from projections.api.main import app

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def test_db() -> Generator[Path, None, None]:
    """Create temporary database with test data.

    Creates:
    - 10 components (dream-studio project)
    - 9 dependencies forming a graph
    - 1 project record
    - 20 tools in tool_registry
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Create schema
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reg_projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS business_projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                project_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_components (
                component_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                component_type TEXT NOT NULL,
                lines INTEGER,
                complexity_score REAL,
                last_analyzed TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_dependencies (
                project_id TEXT NOT NULL,
                from_component TEXT NOT NULL,
                to_component TEXT NOT NULL,
                PRIMARY KEY (project_id, from_component, to_component)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS tool_registry (
                tool_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                source_url TEXT,
                install_command TEXT,
                tags TEXT,
                confidence_score REAL DEFAULT 0.8
            )
        """)

        # Insert project
        conn.execute(
            "INSERT INTO reg_projects (project_id, name, path) VALUES (?, ?, ?)",
            ("dream-studio", "Dream Studio", "/builds/dream-studio"),
        )
        conn.execute(
            "INSERT INTO business_projects (project_id, name, status, project_path, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                "dream-studio",
                "Dream Studio",
                "active",
                "/builds/dream-studio",
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )

        # Insert 10 test components
        components = [
            (
                "comp_1",
                "dream-studio",
                "GraphQuery",
                "lib/graph_query.py",
                "module",
                150,
                2.5,
                "2026-05-05T10:00:00",
            ),
            (
                "comp_2",
                "dream-studio",
                "ToolSearch",
                "lib/tool_search.py",
                "module",
                200,
                3.0,
                "2026-05-05T10:00:00",
            ),
            (
                "comp_3",
                "dream-studio",
                "ApiMain",
                "analytics/api/main.py",
                "module",
                100,
                1.5,
                "2026-05-05T10:00:00",
            ),
            (
                "comp_4",
                "dream-studio",
                "DiscoveryInternal",
                "analytics/api/routes/discovery_internal.py",
                "route",
                175,
                2.8,
                "2026-05-05T10:00:00",
            ),
            (
                "comp_5",
                "dream-studio",
                "DiscoveryExternal",
                "analytics/api/routes/discovery_external.py",
                "route",
                220,
                3.2,
                "2026-05-05T10:00:00",
            ),
            (
                "comp_6",
                "dream-studio",
                "StudioDB",
                "lib/studio_db.py",
                "module",
                130,
                2.0,
                "2026-05-05T10:00:00",
            ),
            (
                "comp_7",
                "dream-studio",
                "Config",
                "lib/config.py",
                "module",
                160,
                2.6,
                "2026-05-05T10:00:00",
            ),
            (
                "comp_8",
                "dream-studio",
                "Utils",
                "lib/utils.py",
                "function",
                190,
                2.9,
                "2026-05-05T10:00:00",
            ),
            (
                "comp_9",
                "dream-studio",
                "Validators",
                "lib/validators.py",
                "function",
                140,
                2.2,
                "2026-05-05T10:00:00",
            ),
            (
                "comp_10",
                "dream-studio",
                "Types",
                "lib/types.py",
                "module",
                180,
                2.7,
                "2026-05-05T10:00:00",
            ),
        ]

        conn.executemany(
            "INSERT INTO pi_components (component_id, project_id, name, path, component_type, lines, complexity_score, last_analyzed)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            components,
        )

        # Insert dependencies (9 edges)
        dependencies = [
            ("dream-studio", "comp_1", "comp_6"),  # GraphQuery -> StudioDB
            ("dream-studio", "comp_2", "comp_6"),  # ToolSearch -> StudioDB
            ("dream-studio", "comp_3", "comp_4"),  # ApiMain -> DiscoveryInternal
            ("dream-studio", "comp_3", "comp_5"),  # ApiMain -> DiscoveryExternal
            ("dream-studio", "comp_4", "comp_1"),  # DiscoveryInternal -> GraphQuery
            ("dream-studio", "comp_5", "comp_2"),  # DiscoveryExternal -> ToolSearch
            ("dream-studio", "comp_6", "comp_7"),  # StudioDB -> Config
            ("dream-studio", "comp_8", "comp_10"),  # Utils -> Types
            ("dream-studio", "comp_9", "comp_10"),  # Validators -> Types
        ]

        conn.executemany(
            "INSERT INTO pi_dependencies (project_id, from_component, to_component) VALUES (?, ?, ?)",
            dependencies,
        )

        # Insert 20 test tools
        tools = [
            (
                "mcp:firecrawl",
                "Firecrawl MCP",
                "mcp",
                "Web scraping and crawling MCP server",
                "https://github.com/firecrawl/mcp",
                "npx @firecrawl/mcp",
                '["web", "scraping"]',
                0.9,
            ),
            (
                "mcp:github",
                "GitHub MCP",
                "mcp",
                "GitHub integration MCP server",
                "https://github.com/modelcontextprotocol/servers",
                "npx @modelcontextprotocol/server-github",
                '["github", "git"]',
                0.95,
            ),
            (
                "python_package:opencv-python",
                "OpenCV",
                "python_package",
                "Computer vision library",
                "https://pypi.org/project/opencv-python/",
                "pip install opencv-python",
                '["video", "image", "cv"]',
                0.9,
            ),
            (
                "python_package:moviepy",
                "MoviePy",
                "python_package",
                "Video editing library",
                "https://pypi.org/project/moviepy/",
                "pip install moviepy",
                '["video", "editing"]',
                0.85,
            ),
            (
                "python_package:ffmpeg-python",
                "FFmpeg Python",
                "python_package",
                "FFmpeg wrapper for Python",
                "https://pypi.org/project/ffmpeg-python/",
                "pip install ffmpeg-python",
                '["video", "ffmpeg"]',
                0.88,
            ),
            (
                "python_package:pillow",
                "Pillow",
                "python_package",
                "Image processing library",
                "https://pypi.org/project/Pillow/",
                "pip install Pillow",
                '["image", "processing"]',
                0.92,
            ),
            (
                "python_package:numpy",
                "NumPy",
                "python_package",
                "Numerical computing library",
                "https://pypi.org/project/numpy/",
                "pip install numpy",
                '["math", "array"]',
                0.95,
            ),
            (
                "python_package:pandas",
                "Pandas",
                "python_package",
                "Data analysis library",
                "https://pypi.org/project/pandas/",
                "pip install pandas",
                '["data", "analysis"]',
                0.93,
            ),
            (
                "python_package:scikit-learn",
                "Scikit-learn",
                "python_package",
                "Machine learning library",
                "https://pypi.org/project/scikit-learn/",
                "pip install scikit-learn",
                '["ml", "classification"]',
                0.91,
            ),
            (
                "python_package:tensorflow",
                "TensorFlow",
                "python_package",
                "Deep learning framework",
                "https://pypi.org/project/tensorflow/",
                "pip install tensorflow",
                '["ml", "deep learning"]',
                0.94,
            ),
            (
                "api:openai",
                "OpenAI API",
                "api",
                "GPT and DALL-E API",
                "https://platform.openai.com/",
                "pip install openai",
                '["ai", "gpt"]',
                0.96,
            ),
            (
                "api:anthropic",
                "Anthropic API",
                "api",
                "Claude API",
                "https://www.anthropic.com/api",
                "pip install anthropic",
                '["ai", "claude"]',
                0.97,
            ),
            (
                "api:stripe",
                "Stripe API",
                "api",
                "Payment processing API",
                "https://stripe.com/docs/api",
                "pip install stripe",
                '["payment", "billing"]',
                0.89,
            ),
            (
                "api:twilio",
                "Twilio API",
                "api",
                "Communication API",
                "https://www.twilio.com/docs/usage/api",
                "pip install twilio",
                '["sms", "phone"]',
                0.87,
            ),
            (
                "saas:notion",
                "Notion",
                "saas",
                "Workspace and collaboration platform",
                "https://notion.so",
                "Browser access",
                '["productivity", "notes"]',
                0.88,
            ),
            (
                "saas:airtable",
                "Airtable",
                "saas",
                "Cloud collaboration database",
                "https://airtable.com",
                "Browser access",
                '["database", "spreadsheet"]',
                0.86,
            ),
            (
                "saas:figma",
                "Figma",
                "saas",
                "Design and prototyping tool",
                "https://figma.com",
                "Browser access",
                '["design", "prototype"]',
                0.92,
            ),
            (
                "saas:vercel",
                "Vercel",
                "saas",
                "Deployment and hosting platform",
                "https://vercel.com",
                "Browser access",
                '["deployment", "hosting"]',
                0.90,
            ),
            (
                "saas:netlify",
                "Netlify",
                "saas",
                "Web hosting platform",
                "https://netlify.com",
                "Browser access",
                '["hosting", "web"]',
                0.89,
            ),
            (
                "saas:cloudflare",
                "Cloudflare",
                "saas",
                "CDN and security platform",
                "https://cloudflare.com",
                "Browser access",
                '["cdn", "security"]',
                0.91,
            ),
        ]

        conn.executemany(
            "INSERT INTO tool_registry (tool_id, name, category, description, source_url, install_command, tags, confidence_score)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            tools,
        )

        conn.commit()
        conn.close()

        yield db_path

    finally:
        # Cleanup
        if db_path.exists():
            db_path.unlink()


def _test_conn_factory(db_path):
    def _get_conn(read_only=False):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    return _get_conn


@pytest.fixture
def client() -> TestClient:
    """Create FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_graph_data():
    """Mock graph data matching GraphResponse schema."""
    return {
        "nodes": [
            {
                "id": "comp_1",
                "name": "GraphQuery",
                "component_type": "module",
                "path": "lib/graph_query.py",
                "lines": 150,
                "complexity_score": 2.5,
                "incoming_edges": 1,
                "outgoing_edges": 1,
                "centrality_score": 0,
            },
            {
                "id": "comp_2",
                "name": "ToolSearch",
                "component_type": "module",
                "path": "lib/tool_search.py",
                "lines": 200,
                "complexity_score": 3.0,
                "incoming_edges": 1,
                "outgoing_edges": 1,
                "centrality_score": 0,
            },
            {
                "id": "comp_6",
                "name": "StudioDB",
                "component_type": "module",
                "path": "lib/studio_db.py",
                "lines": 130,
                "complexity_score": 2.0,
                "incoming_edges": 2,
                "outgoing_edges": 1,
                "centrality_score": 0,
            },
        ],
        "edges": [
            {"source": "comp_1", "target": "comp_6", "dependency_type": "import", "strength": None},
            {"source": "comp_2", "target": "comp_6", "dependency_type": "import", "strength": None},
        ],
    }


# ============================================================================
# TESTS - Internal Discovery Endpoints
# ============================================================================


def test_graph_endpoint(client, test_db, mock_graph_data, monkeypatch):
    """Test GET /api/discovery/internal/graph/{project_id}.

    Verifies:
    - Response has nodes and edges arrays
    - Node structure (id, name, component_type, path)
    - Edge structure (source, target, dependency_type)
    - Node and edge counts are correct
    """
    # Mock database path
    monkeypatch.setattr(
        "projections.api.routes.discovery_internal.get_connection", _test_conn_factory(test_db)
    )

    # Create a mock NetworkX graph with correct node/edge counts
    mock_nx_graph = MagicMock()
    mock_nx_graph.number_of_nodes.return_value = 3
    mock_nx_graph.number_of_edges.return_value = 2

    # Mock both build_graph (returns NetworkX graph) and graph_to_dict (returns dict)
    with (
        patch("projections.api.routes.discovery_internal.graph_query.build_graph") as mock_build,
        patch(
            "projections.api.routes.discovery_internal.graph_query.graph_to_dict"
        ) as mock_to_dict,
    ):
        mock_build.return_value = mock_nx_graph
        mock_to_dict.return_value = mock_graph_data

        response = client.get("/api/discovery/internal/graph/dream-studio")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "nodes" in data
        assert "edges" in data
        assert "node_count" in data
        assert "edge_count" in data

        # Verify counts
        assert data["node_count"] == 3
        assert data["edge_count"] == 2

        # Verify node structure
        assert len(data["nodes"]) == 3
        node = data["nodes"][0]
        assert "id" in node
        assert "name" in node
        assert "component_type" in node
        assert "path" in node
        assert "lines" in node
        assert "complexity_score" in node

        # Verify edge structure
        assert len(data["edges"]) == 2
        edge = data["edges"][0]
        assert "source" in edge
        assert "target" in edge
        assert "dependency_type" in edge


def test_graph_endpoint_404(client, test_db, monkeypatch):
    """Test GET /api/discovery/internal/graph/{project_id} with invalid project."""
    monkeypatch.setattr(
        "projections.api.routes.discovery_internal.get_connection", _test_conn_factory(test_db)
    )

    response = client.get("/api/discovery/internal/graph/nonexistent-project")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ============================================================================
# TESTS - Error Handling
# ============================================================================


def test_graph_endpoint_500_error(client, test_db, monkeypatch):
    """Test GET /api/discovery/internal/graph/{project_id} with build failure."""
    monkeypatch.setattr(
        "projections.api.routes.discovery_internal.get_connection", _test_conn_factory(test_db)
    )

    # Mock build_graph to raise exception
    with patch("projections.api.routes.discovery_internal.graph_query.build_graph") as mock_build:
        mock_build.side_effect = Exception("Graph build failed")

        response = client.get("/api/discovery/internal/graph/dream-studio")

        assert response.status_code == 500
        assert "Failed to build dependency graph" in response.json()["detail"]
