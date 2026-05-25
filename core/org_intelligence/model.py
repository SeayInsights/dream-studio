"""Canonical object model for organization engineering intelligence.

STRICT SCHEMA - NO synthetic types allowed.
All objects must trace to file paths or existing system records.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Set, Any
from enum import Enum


class RelationshipType(Enum):
    """Edge relationship types (STRICT - no additions without justification)."""

    DEPENDENCY = "dependency"  # Module A imports Module B
    USAGE = "usage"  # Module A calls functions from Module B
    SIMILARITY = "similarity"  # Capabilities are similar (graph-derived)
    CAUSALITY = "causality"  # Decision caused Action
    CONTAINS = "contains"  # Repository contains Module
    IMPLEMENTS = "implements"  # Module implements Capability


@dataclass
class Repository:
    """Repository node.

    Traces to: file system directory
    """

    id: str  # Unique ID (repo name or hash)
    name: str  # Repository name
    path: str  # Absolute file path
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Derived metrics (graph-computed)
    module_count: int = 0
    capability_count: int = 0
    loc: int = 0


@dataclass
class Module:
    """Module node (file).

    Traces to: specific file path
    """

    id: str  # Unique ID (repo_id + file_path)
    repo_id: str  # Parent repository
    file_path: str  # Relative path within repo

    # Code structure (from AST)
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)  # Functions, classes exported

    # Capability tags (from normalizer)
    capability_tags: List[str] = field(default_factory=list)

    # Metrics (from existing repo intelligence)
    loc: int = 0
    coupling_score: float = 0.0  # From dependency graph


@dataclass
class Capability:
    """Capability node (functional capability across modules).

    Traces to: one or more modules
    """

    capability_id: str  # Unique ID
    normalized_name: str  # Normalized capability name

    # Source traceability
    source_modules: List[str] = field(default_factory=list)  # Module IDs
    source_repos: Set[str] = field(default_factory=set)  # Repository IDs

    # Metrics (DERIVED from existing signals only)
    risk_score: float = 0.0  # From decision coverage + audit signals
    coupling_score: float = 0.0  # Graph-derived (internal edges)
    reusability_score: float = 0.0  # Graph-derived (external usage)

    # Metadata
    loc: int = 0  # Total lines of code
    module_count: int = 0  # Number of modules implementing


@dataclass
class Edge:
    """Graph edge.

    MUST be traceable to code relationships or existing system data.
    """

    from_node: str  # Source node ID
    to_node: str  # Target node ID
    relationship_type: RelationshipType

    # Edge metadata (source evidence)
    evidence: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0  # Edge weight (for graph algorithms)


@dataclass
class OrganizationGraph:
    """Complete organization-level engineering intelligence graph.

    Deterministic. Fully traceable. NO synthetic entities.
    """

    # Nodes
    repositories: Dict[str, Repository] = field(default_factory=dict)
    modules: Dict[str, Module] = field(default_factory=dict)
    capabilities: Dict[str, Capability] = field(default_factory=dict)

    # Edges
    edges: List[Edge] = field(default_factory=list)

    # Index for fast lookup
    _edges_by_source: Dict[str, List[Edge]] = field(default_factory=dict)
    _edges_by_target: Dict[str, List[Edge]] = field(default_factory=dict)
    _edges_by_type: Dict[RelationshipType, List[Edge]] = field(default_factory=dict)

    def add_repository(self, repo: Repository):
        """Add repository to graph."""
        self.repositories[repo.id] = repo

    def add_module(self, module: Module):
        """Add module to graph."""
        self.modules[module.id] = module

    def add_capability(self, capability: Capability):
        """Add capability to graph."""
        self.capabilities[capability.capability_id] = capability

    def add_edge(self, edge: Edge):
        """Add edge to graph and update indices."""
        self.edges.append(edge)

        # Update indices
        if edge.from_node not in self._edges_by_source:
            self._edges_by_source[edge.from_node] = []
        self._edges_by_source[edge.from_node].append(edge)

        if edge.to_node not in self._edges_by_target:
            self._edges_by_target[edge.to_node] = []
        self._edges_by_target[edge.to_node].append(edge)

        if edge.relationship_type not in self._edges_by_type:
            self._edges_by_type[edge.relationship_type] = []
        self._edges_by_type[edge.relationship_type].append(edge)

    def get_outgoing_edges(self, node_id: str) -> List[Edge]:
        """Get all edges from a node."""
        return self._edges_by_source.get(node_id, [])

    def get_incoming_edges(self, node_id: str) -> List[Edge]:
        """Get all edges to a node."""
        return self._edges_by_target.get(node_id, [])

    def get_edges_by_type(self, rel_type: RelationshipType) -> List[Edge]:
        """Get all edges of a specific type."""
        return self._edges_by_type.get(rel_type, [])

    def get_node_degree(self, node_id: str) -> tuple[int, int]:
        """Get (in_degree, out_degree) for a node."""
        in_degree = len(self.get_incoming_edges(node_id))
        out_degree = len(self.get_outgoing_edges(node_id))
        return in_degree, out_degree

    def to_dict(self) -> Dict:
        """Export graph to dictionary (for JSON serialization)."""
        return {
            "repositories": {
                repo_id: {
                    "id": repo.id,
                    "name": repo.name,
                    "path": repo.path,
                    "module_count": repo.module_count,
                    "capability_count": repo.capability_count,
                    "loc": repo.loc,
                    "metadata": repo.metadata,
                }
                for repo_id, repo in self.repositories.items()
            },
            "modules": {
                mod_id: {
                    "id": mod.id,
                    "repo_id": mod.repo_id,
                    "file_path": mod.file_path,
                    "imports": mod.imports,
                    "exports": mod.exports,
                    "capability_tags": mod.capability_tags,
                    "loc": mod.loc,
                    "coupling_score": mod.coupling_score,
                }
                for mod_id, mod in self.modules.items()
            },
            "capabilities": {
                cap_id: {
                    "capability_id": cap.capability_id,
                    "normalized_name": cap.normalized_name,
                    "source_modules": cap.source_modules,
                    "source_repos": list(cap.source_repos),
                    "risk_score": cap.risk_score,
                    "coupling_score": cap.coupling_score,
                    "reusability_score": cap.reusability_score,
                    "loc": cap.loc,
                    "module_count": cap.module_count,
                }
                for cap_id, cap in self.capabilities.items()
            },
            "edges": [
                {
                    "from": edge.from_node,
                    "to": edge.to_node,
                    "type": edge.relationship_type.value,
                    "weight": edge.weight,
                    "evidence": edge.evidence,
                }
                for edge in self.edges
            ],
        }
