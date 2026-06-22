"""Cross-repository analyzer.

Detects duplicate capabilities, structural divergence, consolidation opportunities.
RULE-BASED. NO ML. Graph-derived only.
"""

from __future__ import annotations
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass, field

from .model import OrganizationGraph, Capability


@dataclass
class DuplicateCapability:
    """Detected duplicate capability across repositories."""

    capability_name: str
    repos: List[str]
    total_loc: int
    module_count: int
    avg_coupling: float
    consolidation_score: float  # 0.0-1.0 (higher = more urgent to consolidate)


@dataclass
class ConsolidationOpportunity:
    """Consolidation opportunity."""

    opportunity_id: str
    capability_name: str
    source_repos: List[str]
    target_repo: str  # Recommended consolidation target
    reason: str
    estimated_effort: str  # S | M | L
    priority_score: float  # 0.0-1.0


@dataclass
class CrossRepoAnalysis:
    """Complete cross-repository analysis."""

    duplicates: List[DuplicateCapability] = field(default_factory=list)
    consolidation_opportunities: List[ConsolidationOpportunity] = field(default_factory=list)
    total_duplication_loc: int = 0
    duplication_rate: float = 0.0  # % of total LOC that is duplicated


class CrossRepoAnalyzer:
    """Analyze cross-repository patterns.

    DETERMINISTIC. Graph-derived metrics only.
    """

    def __init__(self, graph: OrganizationGraph):
        self.graph = graph

    def analyze(self) -> CrossRepoAnalysis:
        """Run complete cross-repository analysis.

        Returns:
            CrossRepoAnalysis
        """
        analysis = CrossRepoAnalysis()

        # Detect duplicates
        analysis.duplicates = self._detect_duplicates()

        # Compute duplication metrics
        analysis.total_duplication_loc = sum(d.total_loc for d in analysis.duplicates)

        total_loc = sum(r.loc for r in self.graph.repositories.values())
        analysis.duplication_rate = (
            analysis.total_duplication_loc / total_loc if total_loc > 0 else 0.0
        )

        # Identify consolidation opportunities
        analysis.consolidation_opportunities = self._identify_consolidation_opportunities(
            analysis.duplicates
        )

        return analysis

    def _detect_duplicates(self) -> List[DuplicateCapability]:
        """Detect duplicate capabilities across repositories.

        Returns:
            List of duplicate capabilities
        """
        duplicates = []

        # Group capabilities by normalized name
        cap_groups: Dict[str, List[Capability]] = {}
        for capability in self.graph.capabilities.values():
            name = capability.normalized_name
            if name not in cap_groups:
                cap_groups[name] = []
            cap_groups[name].append(capability)

        # Find capabilities present in multiple repos
        for cap_name, capabilities in cap_groups.items():
            # Get unique repos
            repos = list(set(repo_id for cap in capabilities for repo_id in cap.source_repos))

            # Duplicate if present in 2+ repos
            if len(repos) >= 2:
                total_loc = sum(cap.loc for cap in capabilities)
                total_modules = sum(cap.module_count for cap in capabilities)
                avg_coupling = sum(cap.coupling_score for cap in capabilities) / len(capabilities)

                # Consolidation score = duplication severity
                # Higher if: more repos, more LOC, higher coupling
                consolidation_score = self._compute_consolidation_score(
                    len(repos), total_loc, avg_coupling
                )

                duplicates.append(
                    DuplicateCapability(
                        capability_name=cap_name,
                        repos=repos,
                        total_loc=total_loc,
                        module_count=total_modules,
                        avg_coupling=avg_coupling,
                        consolidation_score=consolidation_score,
                    )
                )

        # Sort by consolidation score (descending)
        duplicates.sort(key=lambda d: d.consolidation_score, reverse=True)

        return duplicates

    def _compute_consolidation_score(
        self, num_repos: int, total_loc: int, avg_coupling: float
    ) -> float:
        """Compute consolidation urgency score.

        Args:
            num_repos: Number of repos with duplicate
            total_loc: Total lines of code
            avg_coupling: Average coupling score

        Returns:
            Score (0.0-1.0, higher = more urgent)
        """
        # Normalize factors
        repo_factor = min(num_repos / 5.0, 1.0)  # Max at 5 repos
        loc_factor = min(total_loc / 10000.0, 1.0)  # Max at 10k LOC
        coupling_factor = min(avg_coupling / 50.0, 1.0)  # Max at coupling 50

        # Weighted score
        score = (
            0.5 * repo_factor  # 50%: More repos = higher priority
            + 0.3 * loc_factor  # 30%: More code = higher savings
            + 0.2 * coupling_factor  # 20%: Higher coupling = harder to consolidate (lower priority)
        )

        return score

    def _identify_consolidation_opportunities(
        self, duplicates: List[DuplicateCapability]
    ) -> List[ConsolidationOpportunity]:
        """Identify consolidation opportunities from duplicates.

        Args:
            duplicates: List of duplicate capabilities

        Returns:
            List of consolidation opportunities
        """
        opportunities = []

        for dup in duplicates:
            # Recommend target repo: one with largest LOC for this capability
            target_repo = self._select_target_repo(dup.capability_name, dup.repos)

            # Estimate effort
            effort = self._estimate_effort(dup.module_count, dup.total_loc)

            # Generate opportunity
            opp = ConsolidationOpportunity(
                opportunity_id=f"consolidate:{dup.capability_name}",
                capability_name=dup.capability_name,
                source_repos=dup.repos,
                target_repo=target_repo,
                reason=f"Duplicate capability in {len(dup.repos)} repos, {dup.total_loc} LOC total",
                estimated_effort=effort,
                priority_score=dup.consolidation_score,
            )

            opportunities.append(opp)

        return opportunities

    def _select_target_repo(self, capability_name: str, repos: List[str]) -> str:
        """Select target repository for consolidation.

        Args:
            capability_name: Capability name
            repos: Repository IDs

        Returns:
            Target repository ID
        """
        # Find repo with most LOC for this capability
        repo_locs = {}
        for cap in self.graph.capabilities.values():
            if cap.normalized_name == capability_name:
                for repo_id in cap.source_repos:
                    if repo_id in repos:
                        repo_locs[repo_id] = repo_locs.get(repo_id, 0) + cap.loc

        if not repo_locs:
            return repos[0]  # Fallback

        # Return repo with max LOC
        return max(repo_locs.items(), key=lambda x: x[1])[0]

    def _estimate_effort(self, module_count: int, total_loc: int) -> str:
        """Estimate consolidation effort.

        Args:
            module_count: Number of modules
            total_loc: Total lines of code

        Returns:
            Effort estimate (S | M | L)
        """
        # Simple heuristic
        if module_count <= 3 and total_loc <= 1000:
            return "S"
        if module_count <= 10 and total_loc <= 5000:
            return "M"
        return "L"
