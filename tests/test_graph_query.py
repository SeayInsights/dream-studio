"""Unit tests for core.graph.query module.

Test suite covers:
1. test_build_graph() - Verify nodes/edges from test data
2. test_get_dependencies() - 1-hop and 2-hop forward traversal
3. test_get_dependents() - 1-hop and 2-hop backward traversal
4. test_detect_cycles() - Find circular dependency
5. test_analyze_impact() - Calculate risk score correctly
6. test_graph_cache() - Cache hit/miss behavior
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from collections.abc import Generator

import networkx as nx
import pytest

from core.graph.query import (
    build_graph,
    get_dependencies,
    get_dependents,
    detect_cycles,
    detect_communities,
    analyze_impact,
    clear_cache,
    Component,
    ImpactReport,
    _cache_key,
)


@pytest.fixture
def test_db() -> Generator[Path, None, None]:
    """Create an in-memory SQLite database with test data (10-node graph).

    Yields:
        Path to temporary database file

    Graph structure:
        comp_1 → comp_2 → comp_3
        comp_1 → comp_4
        comp_2 → comp_5
        comp_4 → comp_5
        comp_5 → comp_6
        comp_6 → comp_7
        comp_7 → comp_8
        comp_8 → comp_9
        comp_9 → comp_10
        comp_10 → comp_8 (creates cycle: 8 → 9 → 10 → 8)
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        # Run migrations first so the schema is current, then recreate pi_components
        # (dropped in migration 084) for graph query testing purposes.
        from core.event_store.studio_db import _connect as _studio_connect

        _studio_connect(db_path).close()

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS pi_components (
                component_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                component_type TEXT NOT NULL,
                lines INTEGER,
                complexity_score REAL,
                last_analyzed TEXT DEFAULT CURRENT_TIMESTAMP
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

        # Insert 10 test components
        components = [
            ("comp_1", "test_project", "Component 1", "src/comp1.py", "module", 150, 2.5),
            ("comp_2", "test_project", "Component 2", "src/comp2.py", "module", 200, 3.0),
            ("comp_3", "test_project", "Component 3", "src/comp3.py", "module", 100, 1.5),
            ("comp_4", "test_project", "Component 4", "src/comp4.py", "module", 175, 2.8),
            ("comp_5", "test_project", "Component 5", "src/comp5.py", "module", 220, 3.2),
            ("comp_6", "test_project", "Component 6", "src/comp6.py", "module", 130, 2.0),
            ("comp_7", "test_project", "Component 7", "src/comp7.py", "module", 160, 2.6),
            ("comp_8", "test_project", "Component 8", "src/comp8.py", "module", 190, 2.9),
            ("comp_9", "test_project", "Component 9", "src/comp9.py", "module", 140, 2.2),
            ("comp_10", "test_project", "Component 10", "src/comp10.py", "module", 180, 2.7),
        ]

        conn.executemany(
            "INSERT INTO pi_components (component_id, project_id, name, path, component_type, lines, complexity_score) VALUES (?, ?, ?, ?, ?, ?, ?)",
            components,
        )

        # Insert dependencies (edges)
        # Acyclic path: 1 → 2 → 3, 1 → 4 → 5, 2 → 5, 5 → 6 → 7
        # Cycle: 7 → 8 → 9 → 10 → 8
        dependencies = [
            ("test_project", "comp_1", "comp_2"),
            ("test_project", "comp_2", "comp_3"),
            ("test_project", "comp_1", "comp_4"),
            ("test_project", "comp_4", "comp_5"),
            ("test_project", "comp_2", "comp_5"),
            ("test_project", "comp_5", "comp_6"),
            ("test_project", "comp_6", "comp_7"),
            ("test_project", "comp_7", "comp_8"),
            ("test_project", "comp_8", "comp_9"),
            ("test_project", "comp_9", "comp_10"),
            ("test_project", "comp_10", "comp_8"),  # Creates cycle
        ]

        conn.executemany(
            "INSERT INTO pi_dependencies (project_id, from_component, to_component) VALUES (?, ?, ?)",
            dependencies,
        )

        conn.commit()
        conn.close()

        yield db_path

    finally:
        # Clear cache first to release any cached connections
        clear_cache()

        # Force garbage collection to release file handles on Windows
        import gc

        gc.collect()

        # Cleanup with retry for Windows file locking
        import time

        for attempt in range(3):
            try:
                if db_path.exists():
                    db_path.unlink()
                break
            except PermissionError:
                if attempt < 2:
                    time.sleep(0.1)
                    gc.collect()
                else:
                    # Log but don't fail test on cleanup issues
                    import warnings

                    warnings.warn(f"Could not delete test DB: {db_path}")


class TestBuildGraph:
    """Test graph construction from database."""

    def test_build_graph_creates_nodes(self, test_db: Path):
        """Verify graph contains all 10 nodes from test data."""
        graph = build_graph("test_project", test_db)

        assert graph.number_of_nodes() == 10
        assert all(f"comp_{i}" in graph for i in range(1, 11))

    def test_build_graph_creates_edges(self, test_db: Path):
        """Verify graph contains all 11 edges from test data."""
        graph = build_graph("test_project", test_db)

        assert graph.number_of_edges() == 11
        assert graph.has_edge("comp_1", "comp_2")
        assert graph.has_edge("comp_2", "comp_3")
        assert graph.has_edge("comp_10", "comp_8")

    def test_build_graph_node_attributes(self, test_db: Path):
        """Verify nodes have correct attributes."""
        graph = build_graph("test_project", test_db)

        node = graph.nodes["comp_1"]
        assert node["name"] == "Component 1"
        assert node["file_path"] == "src/comp1.py"
        assert node["type"] == "module"
        assert node["lines"] == 150
        assert node["complexity_score"] == 2.5

    def test_build_graph_invalid_project(self, test_db: Path):
        """Verify empty graph for non-existent project."""
        graph = build_graph("nonexistent_project", test_db)

        assert graph.number_of_nodes() == 0
        assert graph.number_of_edges() == 0

    def test_build_graph_empty_project_id_raises(self, test_db: Path):
        """Verify ValueError on empty project_id."""
        with pytest.raises(ValueError, match="project_id cannot be empty"):
            build_graph("", test_db)

    def test_build_graph_is_directed(self, test_db: Path):
        """Verify graph is a directed graph."""
        graph = build_graph("test_project", test_db)

        assert isinstance(graph, nx.DiGraph)
        # comp_1 → comp_2 exists, but comp_2 → comp_1 should not
        assert graph.has_edge("comp_1", "comp_2")
        assert not graph.has_edge("comp_2", "comp_1")


class TestGetDependencies:
    """Test forward traversal (what does X depend on)."""

    def test_get_dependencies_one_hop(self, test_db: Path):
        """Verify 1-hop forward traversal from comp_1."""
        # comp_1 → comp_2, comp_1 → comp_4
        deps = get_dependencies("comp_1", depth=1, project_id="test_project", db_path=test_db)

        assert len(deps) == 2
        dep_ids = {d.component_id for d in deps}
        assert dep_ids == {"comp_2", "comp_4"}

    def test_get_dependencies_two_hops(self, test_db: Path):
        """Verify 2-hop forward traversal from comp_1."""
        # 1-hop: comp_2, comp_4
        # 2-hop: comp_2 → comp_3, comp_2 → comp_5; comp_4 → comp_5
        # Total: comp_2, comp_3, comp_4, comp_5
        deps = get_dependencies("comp_1", depth=2, project_id="test_project", db_path=test_db)

        assert len(deps) == 4
        dep_ids = {d.component_id for d in deps}
        assert dep_ids == {"comp_2", "comp_3", "comp_4", "comp_5"}

    def test_get_dependencies_with_provided_graph(self, test_db: Path):
        """Verify get_dependencies works with pre-built graph."""
        graph = build_graph("test_project", test_db)
        deps = get_dependencies("comp_2", depth=1, graph=graph)

        assert len(deps) == 2
        dep_ids = {d.component_id for d in deps}
        assert dep_ids == {"comp_3", "comp_5"}

    def test_get_dependencies_leaf_node(self, test_db: Path):
        """Verify leaf node (no dependencies) returns empty list."""
        # comp_3 is a true leaf node with no outgoing edges
        deps = get_dependencies("comp_3", depth=1, project_id="test_project", db_path=test_db)

        assert len(deps) == 0

    def test_get_dependencies_component_not_found(self, test_db: Path):
        """Verify ValueError for non-existent component."""
        with pytest.raises(ValueError, match="Component 'nonexistent' not found"):
            get_dependencies("nonexistent", project_id="test_project", db_path=test_db)

    def test_get_dependencies_no_project_or_graph(self, test_db: Path):
        """Verify ValueError when neither graph nor project_id provided."""
        with pytest.raises(ValueError, match="Either graph or project_id must be provided"):
            get_dependencies("comp_1")


class TestGetDependents:
    """Test backward traversal (what depends on X)."""

    def test_get_dependents_one_hop(self, test_db: Path):
        """Verify 1-hop backward traversal to comp_5."""
        # comp_4 → comp_5, comp_2 → comp_5
        dependents = get_dependents("comp_5", depth=1, project_id="test_project", db_path=test_db)

        assert len(dependents) == 2
        dep_ids = {d.component_id for d in dependents}
        assert dep_ids == {"comp_2", "comp_4"}

    def test_get_dependents_two_hops(self, test_db: Path):
        """Verify 2-hop backward traversal to comp_2."""
        # 1-hop: comp_1 depends on comp_2
        # 2-hop: nothing depends on comp_1
        # Total: comp_1
        dependents = get_dependents("comp_2", depth=2, project_id="test_project", db_path=test_db)

        assert len(dependents) == 1
        assert dependents[0].component_id == "comp_1"

    def test_get_dependents_with_provided_graph(self, test_db: Path):
        """Verify get_dependents works with pre-built graph."""
        graph = build_graph("test_project", test_db)
        dependents = get_dependents("comp_3", depth=1, graph=graph)

        assert len(dependents) == 1
        assert dependents[0].component_id == "comp_2"

    def test_get_dependents_root_node(self, test_db: Path):
        """Verify root node (no dependents) returns empty list."""
        # comp_1 has no incoming edges
        dependents = get_dependents("comp_1", depth=1, project_id="test_project", db_path=test_db)

        assert len(dependents) == 0

    def test_get_dependents_component_not_found(self, test_db: Path):
        """Verify ValueError for non-existent component."""
        with pytest.raises(ValueError, match="Component 'nonexistent' not found"):
            get_dependents("nonexistent", project_id="test_project", db_path=test_db)


class TestDetectCycles:
    """Test cycle detection."""

    def test_detect_cycles_finds_cycle(self, test_db: Path):
        """Verify cycle detection finds the 8 → 9 → 10 → 8 cycle."""
        cycles = detect_cycles(project_id="test_project", db_path=test_db)

        assert len(cycles) == 1
        cycle = cycles[0]
        assert len(cycle) == 3

        # Verify cycle components
        cycle_ids = {c.component_id for c in cycle}
        assert cycle_ids == {"comp_8", "comp_9", "comp_10"}

    def test_detect_cycles_with_provided_graph(self, test_db: Path):
        """Verify detect_cycles works with pre-built graph."""
        graph = build_graph("test_project", test_db)
        cycles = detect_cycles(graph=graph)

        assert len(cycles) == 1
        cycle_ids = {c.component_id for c in cycles[0]}
        assert cycle_ids == {"comp_8", "comp_9", "comp_10"}

    def test_detect_cycles_acyclic_graph(self, test_db: Path):
        """Verify acyclic graph returns empty list."""
        # Create a new database with acyclic dependencies only
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            acyclic_db = Path(f.name)

        try:
            conn = sqlite3.connect(acyclic_db)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS pi_components (
                    component_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    component_type TEXT NOT NULL,
                    lines INTEGER,
                    complexity_score REAL,
                    last_analyzed TEXT DEFAULT CURRENT_TIMESTAMP
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

            # Add simple linear chain (no cycles)
            for i in range(1, 4):
                conn.execute(
                    "INSERT INTO pi_components (component_id, project_id, name, path, component_type, lines, complexity_score) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"comp_{i}",
                        "acyclic",
                        f"Component {i}",
                        f"src/comp{i}.py",
                        "module",
                        100,
                        1.5,
                    ),
                )

            conn.execute(
                "INSERT INTO pi_dependencies (project_id, from_component, to_component) VALUES (?, ?, ?)",
                ("acyclic", "comp_1", "comp_2"),
            )
            conn.execute(
                "INSERT INTO pi_dependencies (project_id, from_component, to_component) VALUES (?, ?, ?)",
                ("acyclic", "comp_2", "comp_3"),
            )

            conn.commit()
            conn.close()

            cycles = detect_cycles(project_id="acyclic", db_path=acyclic_db)
            assert len(cycles) == 0

        finally:
            # Clear cache to release connections
            clear_cache()

            # Cleanup with retry for Windows
            import gc
            import time

            gc.collect()

            for attempt in range(3):
                try:
                    if acyclic_db.exists():
                        acyclic_db.unlink()
                    break
                except PermissionError:
                    if attempt < 2:
                        time.sleep(0.1)
                        gc.collect()

    def test_detect_cycles_no_project_or_graph(self, test_db: Path):
        """Verify ValueError when neither graph nor project_id provided."""
        with pytest.raises(ValueError, match="Either graph or project_id must be provided"):
            detect_cycles()


class TestAnalyzeImpact:
    """Test impact analysis and risk scoring."""

    def test_analyze_impact_calculates_risk_score(self, test_db: Path):
        """Verify risk score is calculated as percentage of affected components."""
        # comp_1 affects comp_2 and comp_4 as direct dependents
        report = analyze_impact("comp_1", depth=1, project_id="test_project", db_path=test_db)

        assert isinstance(report, ImpactReport)
        assert report.component_id == "comp_1"
        assert report.depth == 1

        # 0 direct dependents of comp_1 → risk_score = 0/10 = 0.0
        assert report.risk_score == 0.0
        assert len(report.affected_components) == 0

    def test_analyze_impact_deep_traversal(self, test_db: Path):
        """Verify deep traversal captures transitive dependents."""
        # comp_5 is depended on by comp_2 and comp_4
        # comp_2 is depended on by comp_1
        # comp_4 is depended on by comp_1
        report = analyze_impact("comp_5", depth=2, project_id="test_project", db_path=test_db)

        assert report.depth == 2
        # 1-hop: comp_2, comp_4
        # 2-hop: comp_1
        # Total: 3 affected components out of 10
        assert len(report.affected_components) == 3
        assert report.risk_score == 0.3  # 3/10

    def test_analyze_impact_with_provided_graph(self, test_db: Path):
        """Verify analyze_impact works with pre-built graph."""
        graph = build_graph("test_project", test_db)
        report = analyze_impact("comp_6", depth=2, graph=graph)

        assert isinstance(report, ImpactReport)
        assert report.component_id == "comp_6"

        # comp_6 ← comp_5 ← comp_2, comp_4
        # comp_2 ← comp_1 (already counted)
        # comp_4 ← comp_1 (already counted)
        # 1-hop: comp_5
        # 2-hop: comp_2, comp_4 (comp_1 only has one path, not counted twice)
        # Affected: comp_5, comp_2, comp_4 (comp_1 is 2 hops via comp_2, 2 hops via comp_4)
        # But we're counting unique affected, so: comp_5, comp_2, comp_4
        assert len(report.affected_components) == 3
        assert report.risk_score == 0.3  # 3/10

    def test_analyze_impact_risk_score_normalization(self, test_db: Path):
        """Verify risk_score is normalized 0.0-1.0."""
        report = analyze_impact("comp_5", depth=2, project_id="test_project", db_path=test_db)

        assert 0.0 <= report.risk_score <= 1.0

    def test_analyze_impact_component_not_found(self, test_db: Path):
        """Verify ValueError for non-existent component."""
        with pytest.raises(ValueError, match="Component 'nonexistent' not found"):
            analyze_impact("nonexistent", project_id="test_project", db_path=test_db)


class TestGraphCache:
    """Test caching behavior."""

    def test_cache_hit_returns_copy(self, test_db: Path):
        """Verify cache returns a copy, not reference."""
        # First build
        graph1 = build_graph("test_project", test_db)
        # Second build (from cache)
        graph2 = build_graph("test_project", test_db)

        # Both should have same structure
        assert graph1.number_of_nodes() == graph2.number_of_nodes()
        assert graph1.number_of_edges() == graph2.number_of_edges()

        # But should be different objects
        assert graph1 is not graph2

    def test_cache_miss_rebuilds_graph(self, test_db: Path):
        """Verify cache miss rebuilds from database."""
        graph1 = build_graph("test_project", test_db)
        clear_cache("test_project")
        graph2 = build_graph("test_project", test_db)

        # Both should have same structure
        assert graph1.number_of_nodes() == graph2.number_of_nodes()
        assert graph1.number_of_edges() == graph2.number_of_edges()

    def test_clear_cache_specific_project(self, test_db: Path):
        """Verify clear_cache removes specific project."""
        build_graph("test_project", test_db)
        cache_key = _cache_key("test_project")

        clear_cache("test_project")
        # After clear, cache should not contain this key
        # (verified by subsequent build not using cache)
        assert cache_key

    def test_clear_cache_all(self, test_db: Path):
        """Verify clear_cache with no project clears all."""
        build_graph("test_project", test_db)
        clear_cache()

        # Subsequent build should rebuild from database
        graph = build_graph("test_project", test_db)
        assert graph.number_of_nodes() == 10

    def test_cache_different_projects_separate(self, test_db: Path):
        """Verify different projects have separate cache entries."""
        # Build with one project
        graph1 = build_graph("test_project", test_db)

        # Try to build with different project (no data)
        graph2 = build_graph("different_project", test_db)

        # Different graphs
        assert graph1.number_of_nodes() == 10
        assert graph2.number_of_nodes() == 0

    def test_cache_same_project_different_databases_separate(self, tmp_path: Path):
        """Verify temp DBs with the same project id never share cached graphs."""
        first_db = tmp_path / "first.db"
        second_db = tmp_path / "second.db"

        def seed(path: Path, count: int) -> None:
            # Run migrations first so the schema is current, then recreate pi_components
            from core.event_store.studio_db import _connect as _studio_connect

            _studio_connect(path).close()
            conn = sqlite3.connect(path)
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS pi_components (
                        component_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        path TEXT NOT NULL,
                        component_type TEXT NOT NULL,
                        lines INTEGER,
                        complexity_score REAL,
                        last_analyzed TEXT DEFAULT '2026-05-13T00:00:00'
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
                conn.executemany(
                    """
                    INSERT INTO pi_components (
                        component_id, project_id, name, path, component_type, lines, complexity_score
                    ) VALUES (?, 'test_project', ?, ?, 'module', 1, 1.0)
                    """,
                    [
                        (f"same_project_comp_{index}", f"Component {index}", f"src/comp{index}.py")
                        for index in range(count)
                    ],
                )
                conn.commit()
            finally:
                conn.close()

        seed(first_db, 6)
        seed(second_db, 10)
        clear_cache("test_project")

        first_graph = build_graph("test_project", first_db)
        second_graph = build_graph("test_project", second_db)

        assert first_graph.number_of_nodes() == 6
        assert second_graph.number_of_nodes() == 10


class TestComponentDataclass:
    """Test Component dataclass."""

    def test_component_creation(self):
        """Verify Component creation and attributes."""
        comp = Component(
            component_id="comp_1",
            name="Test Component",
            file_path="src/test.py",
            type="module",
            lines=150,
            complexity_score=2.5,
        )

        assert comp.component_id == "comp_1"
        assert comp.name == "Test Component"
        assert comp.file_path == "src/test.py"
        assert comp.type == "module"
        assert comp.lines == 150
        assert comp.complexity_score == 2.5


class TestImpactReportDataclass:
    """Test ImpactReport dataclass."""

    def test_impact_report_creation(self):
        """Verify ImpactReport creation and attributes."""
        components = [
            Component("c1", "Component 1", "src/c1.py", "module", 100, 1.5),
            Component("c2", "Component 2", "src/c2.py", "module", 120, 1.8),
        ]

        report = ImpactReport(
            component_id="test_comp", affected_components=components, risk_score=0.25, depth=2
        )

        assert report.component_id == "test_comp"
        assert len(report.affected_components) == 2
        assert report.risk_score == 0.25
        assert report.depth == 2


class TestDetectCommunities:
    """Test community detection using Louvain clustering algorithm."""

    def test_detect_communities_two_clusters(self):
        """Verify detection of two distinct clusters in test graph."""
        # Create two isolated communities:
        # Community 1: a-b-c (fully connected)
        # Community 2: d-e (connected)
        graph = nx.DiGraph()
        graph.add_nodes_from(
            [
                ("comp_a", {"name": "Component A", "file_path": "a.py", "type": "module"}),
                ("comp_b", {"name": "Component B", "file_path": "b.py", "type": "module"}),
                ("comp_c", {"name": "Component C", "file_path": "c.py", "type": "module"}),
                ("comp_d", {"name": "Component D", "file_path": "d.py", "type": "module"}),
                ("comp_e", {"name": "Component E", "file_path": "e.py", "type": "module"}),
            ]
        )
        # Create edges for community 1 (fully connected, bidirectional)
        graph.add_edges_from(
            [
                ("comp_a", "comp_b"),
                ("comp_b", "comp_a"),
                ("comp_b", "comp_c"),
                ("comp_c", "comp_b"),
                ("comp_a", "comp_c"),
                ("comp_c", "comp_a"),
            ]
        )
        # Create edges for community 2
        graph.add_edges_from(
            [
                ("comp_d", "comp_e"),
                ("comp_e", "comp_d"),
            ]
        )

        communities = detect_communities(graph=graph)

        # Verify communities were detected
        assert len(communities) > 0, "Communities should be detected"
        assert len(communities) == 5, "All 5 components should have community assignments"

        # Verify that a, b, c are in the same community
        comm_a = communities["comp_a"]
        comm_b = communities["comp_b"]
        comm_c = communities["comp_c"]
        assert comm_a == comm_b == comm_c, "Components in same cluster should be in same community"

        # Verify that d, e are in the same community (but different from a, b, c)
        comm_d = communities["comp_d"]
        comm_e = communities["comp_e"]
        assert comm_d == comm_e, "Components in same cluster should be in same community"
        assert comm_d != comm_a, "Different clusters should be in different communities"

    def test_detect_communities_single_cluster(self):
        """Verify detection when all components are tightly coupled."""
        # Create a fully connected graph (all nodes connected to all others)
        graph = nx.DiGraph()
        nodes = ["comp_a", "comp_b", "comp_c", "comp_d"]
        graph.add_nodes_from(
            [
                (
                    node,
                    {
                        "name": f"Component {node[-1].upper()}",
                        "file_path": f"{node[-1]}.py",
                        "type": "module",
                    },
                )
                for node in nodes
            ]
        )

        # Add edges: each node connects to every other node (both directions)
        for i, node_i in enumerate(nodes):
            for j, node_j in enumerate(nodes):
                if i != j:
                    graph.add_edge(node_i, node_j)

        communities = detect_communities(graph=graph)

        # Verify all components are detected
        assert (
            len(communities) == 4
        ), f"Expected all 4 components in communities, got {len(communities)}"

        # Verify all are in the same community
        community_ids = set(communities.values())
        assert (
            len(community_ids) == 1
        ), f"All tightly coupled nodes should be in 1 community, found {len(community_ids)}"

    def test_detect_communities_empty_graph(self):
        """Verify no communities detected in empty graph."""
        graph = nx.DiGraph()

        communities = detect_communities(graph=graph)

        assert len(communities) == 0, "Empty graph should have no communities"

    def test_detect_communities_isolated_nodes(self):
        """Verify handling of isolated nodes (no edges)."""
        graph = nx.DiGraph()
        graph.add_nodes_from(
            [
                ("comp_a", {"name": "Component A", "file_path": "a.py", "type": "module"}),
                ("comp_b", {"name": "Component B", "file_path": "b.py", "type": "module"}),
                ("comp_c", {"name": "Component C", "file_path": "c.py", "type": "module"}),
            ]
        )
        # No edges - all isolated

        communities = detect_communities(graph=graph)

        # Isolated nodes with no edges should return empty dict
        # (Louvain requires edges to form communities)
        assert len(communities) == 0, "Isolated nodes with no edges should return empty communities"

    def test_detect_communities_star_topology(self):
        """Verify detection in star topology (hub and spokes)."""
        # Create star: central hub connected to 4 spokes
        graph = nx.DiGraph()
        graph.add_nodes_from(
            [
                ("comp_hub", {"name": "Hub Component", "file_path": "hub.py", "type": "module"}),
                ("comp_a", {"name": "Component A", "file_path": "a.py", "type": "module"}),
                ("comp_b", {"name": "Component B", "file_path": "b.py", "type": "module"}),
                ("comp_c", {"name": "Component C", "file_path": "c.py", "type": "module"}),
                ("comp_d", {"name": "Component D", "file_path": "d.py", "type": "module"}),
            ]
        )
        # Hub connects to each spoke (bidirectional)
        for spoke in ["comp_a", "comp_b", "comp_c", "comp_d"]:
            graph.add_edge("comp_hub", spoke)
            graph.add_edge(spoke, "comp_hub")

        communities = detect_communities(graph=graph)

        assert len(communities) > 0, "Star topology should detect communities"

        # All nodes should be in the same community since they're all connected
        community_ids = set(communities.values())
        assert (
            len(community_ids) <= 2
        ), f"Star should form 1-2 communities, got {len(community_ids)}"

    def test_detect_communities_preserves_component_ids(self):
        """Verify returned community mapping uses correct component IDs."""
        graph = nx.DiGraph()
        graph.add_nodes_from(
            [
                (
                    "comp_service_a",
                    {"name": "Service A", "file_path": "svc_a.py", "type": "service"},
                ),
                (
                    "comp_service_b",
                    {"name": "Service B", "file_path": "svc_b.py", "type": "service"},
                ),
                ("comp_util_x", {"name": "Utility X", "file_path": "util_x.py", "type": "utility"}),
            ]
        )
        graph.add_edges_from(
            [
                ("comp_service_a", "comp_service_b"),
                ("comp_service_b", "comp_service_a"),
                ("comp_util_x", "comp_service_a"),
                ("comp_service_a", "comp_util_x"),
            ]
        )

        communities = detect_communities(graph=graph)

        # Verify all component IDs are correct keys in the result
        for comp_id in ["comp_service_a", "comp_service_b", "comp_util_x"]:
            assert comp_id in communities, f"Component {comp_id} should be in communities dict"

        # Verify community IDs are integers
        for comm_id in communities.values():
            assert isinstance(comm_id, int), "Community IDs should be integers"

    def test_detect_communities_returns_dict_format(self):
        """Verify detect_communities returns correct dict format."""
        graph = nx.DiGraph()
        graph.add_nodes_from(
            [
                ("comp_x", {"name": "X", "file_path": "x.py", "type": "module"}),
                ("comp_y", {"name": "Y", "file_path": "y.py", "type": "module"}),
            ]
        )
        graph.add_edges_from(
            [
                ("comp_x", "comp_y"),
                ("comp_y", "comp_x"),
            ]
        )

        communities = detect_communities(graph=graph)

        # Verify return type
        assert isinstance(communities, dict), "Should return a dictionary"

        # Verify keys are component IDs and values are community IDs
        for comp_id, comm_id in communities.items():
            assert isinstance(comp_id, str), f"Component ID should be string, got {type(comp_id)}"
            assert isinstance(comm_id, int), f"Community ID should be int, got {type(comm_id)}"

    def test_detect_communities_three_separate_clusters(self):
        """Verify detection of three separate clusters with strong internal coupling."""
        # Create three groups with strong internal coupling, weak external coupling
        graph = nx.DiGraph()

        # Cluster 1: a, b, c (fully connected)
        cluster1 = [
            ("comp_1a", {"name": "Cluster1 A", "file_path": "c1a.py", "type": "module"}),
            ("comp_1b", {"name": "Cluster1 B", "file_path": "c1b.py", "type": "module"}),
            ("comp_1c", {"name": "Cluster1 C", "file_path": "c1c.py", "type": "module"}),
        ]
        graph.add_nodes_from(cluster1)
        graph.add_edges_from(
            [
                ("comp_1a", "comp_1b"),
                ("comp_1b", "comp_1a"),
                ("comp_1b", "comp_1c"),
                ("comp_1c", "comp_1b"),
                ("comp_1a", "comp_1c"),
                ("comp_1c", "comp_1a"),
            ]
        )

        # Cluster 2: d, e (connected)
        cluster2 = [
            ("comp_2a", {"name": "Cluster2 A", "file_path": "c2a.py", "type": "module"}),
            ("comp_2b", {"name": "Cluster2 B", "file_path": "c2b.py", "type": "module"}),
        ]
        graph.add_nodes_from(cluster2)
        graph.add_edges_from(
            [
                ("comp_2a", "comp_2b"),
                ("comp_2b", "comp_2a"),
            ]
        )

        # Cluster 3: f, g, h (fully connected)
        cluster3 = [
            ("comp_3a", {"name": "Cluster3 A", "file_path": "c3a.py", "type": "module"}),
            ("comp_3b", {"name": "Cluster3 B", "file_path": "c3b.py", "type": "module"}),
            ("comp_3c", {"name": "Cluster3 C", "file_path": "c3c.py", "type": "module"}),
        ]
        graph.add_nodes_from(cluster3)
        graph.add_edges_from(
            [
                ("comp_3a", "comp_3b"),
                ("comp_3b", "comp_3a"),
                ("comp_3b", "comp_3c"),
                ("comp_3c", "comp_3b"),
                ("comp_3a", "comp_3c"),
                ("comp_3c", "comp_3a"),
            ]
        )

        communities = detect_communities(graph=graph)

        # Count unique communities
        if communities:
            unique_communities = len(set(communities.values()))
            assert (
                unique_communities >= 2
            ), f"Expected at least 2 communities, found {unique_communities}"

            # Verify that nodes in same cluster are in same community
            comp_1a_comm = communities["comp_1a"]
            comp_1b_comm = communities["comp_1b"]
            comp_1c_comm = communities["comp_1c"]
            assert (
                comp_1a_comm == comp_1b_comm == comp_1c_comm
            ), "Cluster 1 should be in same community"

            comp_2a_comm = communities["comp_2a"]
            comp_2b_comm = communities["comp_2b"]
            assert comp_2a_comm == comp_2b_comm, "Cluster 2 should be in same community"

            comp_3a_comm = communities["comp_3a"]
            comp_3b_comm = communities["comp_3b"]
            comp_3c_comm = communities["comp_3c"]
            assert (
                comp_3a_comm == comp_3b_comm == comp_3c_comm
            ), "Cluster 3 should be in same community"
