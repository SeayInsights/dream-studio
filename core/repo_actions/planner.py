"""Action planner - orchestrates action generation and prioritization."""

from __future__ import annotations
from collections import defaultdict
from typing import Dict, List

from .model import RepoAction, RepoActionPlan, SystemPriorityMap, EffortEstimate
from .generator import ActionGenerator


class RepoActionPlanner:
    """Orchestrate action generation for a repository."""

    def __init__(self, repo_name: str):
        self.repo_name = repo_name
        self.generator = ActionGenerator(repo_name)

    def generate_plan(
        self,
        coverage_data: Dict[str, any],
        integrity_data: Dict[str, any],
        capability_data: Dict[str, any],
        coupling_data: Dict[str, any],
    ) -> RepoActionPlan:
        """Generate complete action plan from system data.

        Args:
            coverage_data: Coverage audit results
            integrity_data: Integrity audit results
            capability_data: Capability extraction results
            coupling_data: Coupling analysis results

        Returns:
            RepoActionPlan with prioritized actions
        """
        # Generate actions from each signal source
        coverage_actions = self.generator.generate_from_coverage_gaps(
            coverage_data.get("missing_instrumentation", [])
        )

        orphan_actions = self.generator.generate_from_orphan_decisions(
            integrity_data.get("orphan_decisions", []), integrity_data.get("decision_data", {})
        )

        coupling_actions = self.generator.generate_from_coupling_hotspots(
            coupling_data.get("hotspots", [])
        )

        extract_actions = self.generator.generate_from_service_boundaries(
            capability_data.get("service_boundaries", [])
        )

        # Add all actions
        self.generator.add_actions(coverage_actions)
        self.generator.add_actions(orphan_actions)
        self.generator.add_actions(coupling_actions)
        self.generator.add_actions(extract_actions)

        # Get all actions and sort by priority
        all_actions = self.generator.get_all_actions()
        sorted_actions = sorted(all_actions, key=lambda a: a.priority_score, reverse=True)[
            :20
        ]  # Top 20 max

        # Group by subsystem
        subsystem_groups = defaultdict(list)
        for action in sorted_actions:
            subsystem = self._extract_subsystem(action.target)
            subsystem_groups[subsystem].append(action)

        # Calculate total effort
        effort_counts = {EffortEstimate.SMALL: 0, EffortEstimate.MEDIUM: 0, EffortEstimate.LARGE: 0}
        for action in sorted_actions:
            effort_counts[action.estimated_effort] += 1

        total_effort = (
            f"{effort_counts[EffortEstimate.SMALL]}S + "
            f"{effort_counts[EffortEstimate.MEDIUM]}M + "
            f"{effort_counts[EffortEstimate.LARGE]}L"
        )

        # Count high priority
        high_priority = sum(1 for a in sorted_actions if a.priority_score > 0.7)

        return RepoActionPlan(
            repo_name=self.repo_name,
            actions=sorted_actions,
            total_estimated_effort=total_effort,
            high_priority_count=high_priority,
            subsystem_grouping=dict(subsystem_groups),
        )

    def _extract_subsystem(self, target: str) -> str:
        """Extract subsystem name from target.

        Args:
            target: Target module/file path

        Returns:
            Subsystem name
        """
        # Simple heuristic: first part of module path
        parts = target.replace("/", ".").replace("\\", ".").split(".")
        if len(parts) > 1:
            return parts[0]
        return "core"


class SystemWideActionPlanner:
    """Generate system-wide prioritization map."""

    def __init__(self):
        self.repo_plans: Dict[str, RepoActionPlan] = {}

    def add_repo_plan(self, plan: RepoActionPlan):
        """Add a repository plan.

        Args:
            plan: Repository action plan
        """
        self.repo_plans[plan.repo_name] = plan

    def generate_system_map(self) -> SystemPriorityMap:
        """Generate system-wide priority map.

        Returns:
            SystemPriorityMap with top actions across all repos
        """
        # Collect all actions
        all_actions = []
        for plan in self.repo_plans.values():
            all_actions.extend(plan.actions)

        # Sort by priority
        sorted_actions = sorted(all_actions, key=lambda a: a.priority_score, reverse=True)[
            :10
        ]  # Top 10 system-wide

        # Group by capability domain
        by_capability = defaultdict(list)
        for action in sorted_actions:
            # Extract domain from capability_ids
            if action.capability_ids:
                domain = action.capability_ids[0].split("_")[0]
                by_capability[domain].append(action)
            else:
                by_capability["infrastructure"].append(action)

        # Dependency-aware ordering
        # For now, just preserve priority order
        # TODO: Could add dependency graph traversal here
        dependency_ordered = sorted_actions

        return SystemPriorityMap(
            top_actions=sorted_actions,
            by_capability_domain=dict(by_capability),
            dependency_ordered_actions=dependency_ordered,
        )
