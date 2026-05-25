"""Role-based insight engine.

Generates deterministic views for different stakeholders.
NO LLM narration. Pure structured findings + metrics.
"""

from __future__ import annotations
from typing import Dict, List
from dataclasses import dataclass, field

from .model import OrganizationGraph
from .cross_repo_analyzer import CrossRepoAnalysis


@dataclass
class VPMetrics:
    """VP Engineering metrics (deterministic KPIs)."""

    system_health_score: float  # 0.0-1.0
    risk_hotspots: List[str]  # Capability IDs with high risk
    duplication_rate: float  # % of LOC that is duplicated
    consolidation_candidates: int  # Number of opportunities
    total_repositories: int
    total_modules: int
    total_capabilities: int
    total_loc: int


@dataclass
class EngineeringDebtMap:
    """Engineering-focused debt map."""

    coupling_hotspots: List[Dict]  # High coupling modules
    refactor_targets: List[str]  # Module IDs needing refactoring
    dependency_explosion_points: List[str]  # Modules with high fan-out


@dataclass
class SecurityComplianceView:
    """Security/compliance view."""

    guardrail_coverage: float  # % of modules with guardrails
    missing_decision_instrumentation: List[str]  # Module IDs
    risk_exposure_nodes: List[str]  # Capability IDs with high risk


@dataclass
class ProductView:
    """Product-focused view."""

    reusable_capability_clusters: List[Dict]
    productization_candidates: List[str]  # Capability IDs
    cross_repo_reusable_modules: List[str]


class RoleBasedInsightEngine:
    """Generate role-based insights from organization graph.

    DETERMINISTIC. NO LLM. Pure graph analytics.
    """

    def __init__(self, graph: OrganizationGraph, cross_repo_analysis: CrossRepoAnalysis):
        self.graph = graph
        self.cross_repo_analysis = cross_repo_analysis

    def generate_vp_metrics(self) -> VPMetrics:
        """Generate VP Engineering metrics.

        Returns:
            VPMetrics
        """
        # System health = (1 - avg_risk) * (1 - duplication_rate)
        avg_risk = self._compute_average_risk()
        system_health = (1.0 - avg_risk) * (1.0 - self.cross_repo_analysis.duplication_rate)

        # Risk hotspots = capabilities with risk > 0.7
        risk_hotspots = [
            cap.capability_id for cap in self.graph.capabilities.values() if cap.risk_score > 0.7
        ]

        return VPMetrics(
            system_health_score=system_health,
            risk_hotspots=risk_hotspots,
            duplication_rate=self.cross_repo_analysis.duplication_rate,
            consolidation_candidates=len(self.cross_repo_analysis.consolidation_opportunities),
            total_repositories=len(self.graph.repositories),
            total_modules=len(self.graph.modules),
            total_capabilities=len(self.graph.capabilities),
            total_loc=sum(r.loc for r in self.graph.repositories.values()),
        )

    def generate_engineering_debt_map(self) -> EngineeringDebtMap:
        """Generate engineering debt map.

        Returns:
            EngineeringDebtMap
        """
        # Coupling hotspots = modules with coupling > 20
        coupling_hotspots = [
            {"module_id": mod.id, "file_path": mod.file_path, "coupling_score": mod.coupling_score}
            for mod in self.graph.modules.values()
            if mod.coupling_score > 20
        ]
        coupling_hotspots.sort(key=lambda x: x["coupling_score"], reverse=True)

        # Refactor targets = same as coupling hotspots
        refactor_targets = [h["module_id"] for h in coupling_hotspots[:20]]

        # Dependency explosion = modules with high out-degree
        explosion_points = []
        for mod_id in self.graph.modules:
            _, out_degree = self.graph.get_node_degree(mod_id)
            if out_degree > 15:
                explosion_points.append(mod_id)

        return EngineeringDebtMap(
            coupling_hotspots=coupling_hotspots[:50],  # Top 50
            refactor_targets=refactor_targets,
            dependency_explosion_points=explosion_points,
        )

    def generate_security_compliance_view(self) -> SecurityComplianceView:
        """Generate security/compliance view.

        Returns:
            SecurityComplianceView
        """
        # Guardrail coverage = % of modules with "compliance_system" capability
        compliance_modules = [
            mod.id
            for mod in self.graph.modules.values()
            if "compliance_system" in mod.capability_tags
        ]
        guardrail_coverage = (
            len(compliance_modules) / len(self.graph.modules) if self.graph.modules else 0.0
        )

        # Missing instrumentation = modules without decision_system capability
        decision_modules = set(
            mod.id
            for mod in self.graph.modules.values()
            if "decision_system" in mod.capability_tags
        )
        missing_instrumentation = [
            mod.id for mod in self.graph.modules.values() if mod.id not in decision_modules
        ][
            :100
        ]  # Top 100

        # Risk exposure = capabilities with risk > 0.5
        risk_exposure = [
            cap.capability_id for cap in self.graph.capabilities.values() if cap.risk_score > 0.5
        ]

        return SecurityComplianceView(
            guardrail_coverage=guardrail_coverage,
            missing_decision_instrumentation=missing_instrumentation,
            risk_exposure_nodes=risk_exposure,
        )

    def generate_product_view(self) -> ProductView:
        """Generate product view.

        Returns:
            ProductView
        """
        # Reusable clusters = capabilities with reusability > 0.3
        reusable_clusters = [
            {
                "capability_id": cap.capability_id,
                "capability_name": cap.normalized_name,
                "reusability_score": cap.reusability_score,
                "module_count": cap.module_count,
                "loc": cap.loc,
            }
            for cap in self.graph.capabilities.values()
            if cap.reusability_score > 0.3
        ]
        reusable_clusters.sort(key=lambda x: x["reusability_score"], reverse=True)

        # Productization candidates = capabilities in multiple repos with low coupling
        productization_candidates = [
            cap.capability_id
            for cap in self.graph.capabilities.values()
            if len(cap.source_repos) >= 2 and cap.coupling_score < 10
        ]

        # Cross-repo reusable = modules used by multiple capabilities
        module_usage: Dict[str, int] = {}
        for cap in self.graph.capabilities.values():
            for mod_id in cap.source_modules:
                module_usage[mod_id] = module_usage.get(mod_id, 0) + 1

        cross_repo_reusable = [mod_id for mod_id, count in module_usage.items() if count >= 2]

        return ProductView(
            reusable_capability_clusters=reusable_clusters[:20],
            productization_candidates=productization_candidates,
            cross_repo_reusable_modules=cross_repo_reusable,
        )

    def _compute_average_risk(self) -> float:
        """Compute average risk across capabilities.

        Returns:
            Average risk (0.0-1.0)
        """
        if not self.graph.capabilities:
            return 0.0

        total_risk = sum(cap.risk_score for cap in self.graph.capabilities.values())
        return total_risk / len(self.graph.capabilities)
