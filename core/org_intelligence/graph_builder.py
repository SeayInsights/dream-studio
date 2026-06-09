"""Organization graph builder.

Builds complete directed graph from repositories, modules, capabilities.
Computes graph-derived metrics. NO synthetic scoring.
"""

from __future__ import annotations
from typing import Dict, List

from .model import Repository, Module, Capability, Edge, OrganizationGraph, RelationshipType


class OrganizationGraphBuilder:
    """Build organization-level engineering intelligence graph.

    STRICTLY deterministic. All metrics graph-derived or from existing signals.
    """

    def __init__(self):
        self.graph = OrganizationGraph()

    def build_graph(
        self,
        repositories: Dict[str, Repository],
        modules: Dict[str, Module],
        capabilities: Dict[str, Capability],
        edges: List[Edge],
    ) -> OrganizationGraph:
        """Build complete organization graph.

        Args:
            repositories: Repository nodes
            modules: Module nodes
            capabilities: Capability nodes
            edges: Initial edges (CONTAINS, DEPENDENCY)

        Returns:
            Complete organization graph
        """
        # Add nodes
        for repo in repositories.values():
            self.graph.add_repository(repo)

        for module in modules.values():
            self.graph.add_module(module)

        for capability in capabilities.values():
            self.graph.add_capability(capability)

        # Add initial edges
        for edge in edges:
            self.graph.add_edge(edge)

        # Add IMPLEMENTS edges: Module → Capability
        for capability in capabilities.values():
            for module_id in capability.source_modules:
                if module_id in modules:
                    self.graph.add_edge(
                        Edge(
                            from_node=module_id,
                            to_node=capability.capability_id,
                            relationship_type=RelationshipType.IMPLEMENTS,
                            evidence={"capability": capability.normalized_name},
                        )
                    )

        # Compute graph-derived metrics
        self._compute_module_coupling()
        self._compute_capability_metrics()
        self._update_repository_metrics()

        return self.graph

    def _compute_module_coupling(self):
        """Compute coupling scores for modules (graph-derived)."""
        for module_id, module in self.graph.modules.items():
            # Coupling = incoming + outgoing dependency edges
            in_edges = [
                e
                for e in self.graph.get_incoming_edges(module_id)
                if e.relationship_type == RelationshipType.DEPENDENCY
            ]
            out_edges = [
                e
                for e in self.graph.get_outgoing_edges(module_id)
                if e.relationship_type == RelationshipType.DEPENDENCY
            ]

            # Coupling score = total dependencies
            module.coupling_score = len(in_edges) + len(out_edges)

    def _compute_capability_metrics(self):
        """Compute metrics for capabilities (graph-derived)."""
        for cap_id, capability in self.graph.capabilities.items():
            # Coupling score = average coupling of implementing modules
            module_couplings = [
                self.graph.modules[mid].coupling_score
                for mid in capability.source_modules
                if mid in self.graph.modules
            ]
            capability.coupling_score = (
                sum(module_couplings) / len(module_couplings) if module_couplings else 0.0
            )

            # Reusability score = number of modules implementing / total modules
            capability.reusability_score = (
                capability.module_count / len(self.graph.modules) if self.graph.modules else 0.0
            )

            # Risk score will be set externally from decision coverage signals

    def _update_repository_metrics(self):
        """Update repository metrics from graph."""
        for repo_id, repo in self.graph.repositories.items():
            # Module count
            repo_modules = [m for m in self.graph.modules.values() if m.repo_id == repo_id]
            repo.module_count = len(repo_modules)

            # Capability count (distinct capabilities)
            capability_ids = set()
            for module in repo_modules:
                for cap_tag in module.capability_tags:
                    capability_ids.add(f"cap:{cap_tag}")

            repo.capability_count = len(capability_ids)

            # LOC (total)
            repo.loc = sum(m.loc for m in repo_modules)

    def integrate_decision_signals(self, decision_coverage_map: Dict[str, float]):
        """Integrate decision coverage signals into capability risk scores.

        Args:
            decision_coverage_map: module_id → coverage_ratio (0.0-1.0)
        """
        for cap_id, capability in self.graph.capabilities.items():
            # Risk score = 1.0 - average coverage across modules
            coverages = [decision_coverage_map.get(mid, 0.0) for mid in capability.source_modules]

            avg_coverage = sum(coverages) / len(coverages) if coverages else 0.0
            capability.risk_score = 1.0 - avg_coverage  # Higher risk = lower coverage

    def get_graph(self) -> OrganizationGraph:
        """Get built graph."""
        return self.graph
