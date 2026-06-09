"""Action generator - synthesizes actions from existing system outputs."""

from __future__ import annotations
import uuid
from typing import Dict, List

from .model import RepoAction, ActionType, RiskLevel, EffortEstimate, SupportingSignal
from .priority import calculate_action_priority


class ActionGenerator:
    """Generate actionable engineering tasks from system analysis."""

    def __init__(self, repo_name: str):
        self.repo_name = repo_name
        self.actions: List[RepoAction] = []

    def generate_from_coverage_gaps(self, coverage_gaps: List[any]) -> List[RepoAction]:
        """Generate instrumentation actions from coverage gaps.

        Args:
            coverage_gaps: List of missing instrumentation points from audit system

        Returns:
            List of instrument actions
        """
        actions = []

        for gap in coverage_gaps:
            # Handle both dict and object formats
            if hasattr(gap, "file"):
                # DiscoveredDecisionPoint object
                file_path = gap.file
                line_no = gap.line
                decision_type = gap.decision_type_guess
                confidence = gap.confidence
            else:
                # Dict format
                file_path = gap.get("file", "")
                line_no = gap.get("line", 0)
                decision_type = gap.get("decision_type_guess", "unknown")
                confidence = gap.get("confidence", 0.0)

            # Calculate priority
            priority = calculate_action_priority(
                {
                    "risk_score": 0.7,  # Missing instrumentation is high risk
                    "missing_instrumentation_count": 1,
                }
            )

            # Create supporting signal
            signal = SupportingSignal(
                signal_type="coverage",
                signal_id=f"{file_path}:{line_no}",
                description=f"Missing {decision_type} decision at line {line_no}",
                relevance=confidence,
            )

            action = RepoAction(
                action_id=str(uuid.uuid4())[:8],
                repo=self.repo_name,
                target=file_path,
                action_type=ActionType.INSTRUMENT,
                priority_score=priority,
                rationale={
                    "reason": f"Missing decision instrumentation for {decision_type}",
                    "source": "coverage_audit",
                    "line": line_no,
                    "confidence": confidence,
                },
                supporting_signals=[signal],
                estimated_effort=EffortEstimate.SMALL,
                risk_level=RiskLevel.LOW,
                expected_impact=f"Add decision transparency for {decision_type} logic",
                coverage_finding_ids=[f"{file_path}:{line_no}"],
            )

            if action.is_traceable():
                actions.append(action)

        return actions

    def generate_from_orphan_decisions(
        self, orphan_decisions: List[str], decision_data: Dict[str, any]
    ) -> List[RepoAction]:
        """Generate fix actions from orphan decisions.

        Args:
            orphan_decisions: List of decision IDs without event links
            decision_data: Decision metadata by ID

        Returns:
            List of fix actions
        """
        actions = []

        for decision_id in orphan_decisions:
            data = decision_data.get(decision_id, {})
            decision_type = data.get("decision_type", "unknown")
            subsystem = data.get("subsystem", "unknown")

            priority = calculate_action_priority({"risk_score": 0.5, "orphan_decision_count": 1})

            signal = SupportingSignal(
                signal_type="decision",
                signal_id=decision_id,
                description=f"Orphan decision {decision_type} without event link",
                relevance=0.8,
            )

            action = RepoAction(
                action_id=str(uuid.uuid4())[:8],
                repo=self.repo_name,
                target=subsystem,
                action_type=ActionType.FIX,
                priority_score=priority,
                rationale={
                    "reason": "Decision emitted but no causal event link",
                    "source": "integrity_audit",
                    "decision_type": decision_type,
                },
                supporting_signals=[signal],
                estimated_effort=EffortEstimate.SMALL,
                risk_level=RiskLevel.LOW,
                expected_impact="Link decision to causal event for audit trail",
                decision_ids=[decision_id],
            )

            if action.is_traceable():
                actions.append(action)

        return actions

    def generate_from_coupling_hotspots(
        self, coupling_hotspots: List[Dict[str, any]]
    ) -> List[RepoAction]:
        """Generate refactor actions from coupling hotspots.

        Args:
            coupling_hotspots: List of high-coupling modules

        Returns:
            List of refactor actions
        """
        actions = []

        for hotspot in coupling_hotspots[:10]:  # Top 10 only
            module = hotspot.get("module", "")
            coupling_score = hotspot.get("coupling_score", 0)
            incoming = hotspot.get("incoming_deps", 0)
            outgoing = hotspot.get("outgoing_deps", 0)

            # Only refactor if significantly coupled
            if coupling_score < 10:
                continue

            priority = calculate_action_priority(
                {"coupling_score": coupling_score, "risk_score": min(1.0, coupling_score / 50.0)}
            )

            signal = SupportingSignal(
                signal_type="coupling",
                signal_id=module,
                description=f"High coupling: {incoming} in, {outgoing} out",
                relevance=min(1.0, coupling_score / 100.0),
            )

            action = RepoAction(
                action_id=str(uuid.uuid4())[:8],
                repo=self.repo_name,
                target=module,
                action_type=ActionType.REFACTOR,
                priority_score=priority,
                rationale={
                    "reason": "High coupling reduces modularity and testability",
                    "source": "dependency_graph",
                    "coupling_score": coupling_score,
                    "incoming_deps": incoming,
                    "outgoing_deps": outgoing,
                },
                supporting_signals=[signal],
                estimated_effort=(
                    EffortEstimate.LARGE if coupling_score > 30 else EffortEstimate.MEDIUM
                ),
                risk_level=RiskLevel.HIGH if incoming > 10 else RiskLevel.MEDIUM,
                expected_impact=f"Reduce coupling from {coupling_score} to <10",
                capability_ids=[module],  # Use module as capability proxy
            )

            if action.is_traceable():
                actions.append(action)

        return actions

    def generate_from_service_boundaries(
        self, service_boundaries: List[Dict[str, any]]
    ) -> List[RepoAction]:
        """Generate extract actions from service boundary recommendations.

        Args:
            service_boundaries: List of extract-as-service candidates

        Returns:
            List of extract actions
        """
        actions = []

        for boundary in service_boundaries[:5]:  # Top 5 only
            capability = boundary.get("capability", "")
            reusability = boundary.get("reusability", 0.0)
            recommendation = boundary.get("recommendation", "")

            # Only extract if high reusability
            if reusability < 0.7:
                continue

            priority = calculate_action_priority(
                {"reusability": reusability, "product_impact_score": reusability}
            )

            signal = SupportingSignal(
                signal_type="capability",
                signal_id=capability,
                description=f"High reusability ({reusability:.0%}): {recommendation}",
                relevance=reusability,
            )

            action = RepoAction(
                action_id=str(uuid.uuid4())[:8],
                repo=self.repo_name,
                target=capability,
                action_type=ActionType.EXTRACT,
                priority_score=priority,
                rationale={
                    "reason": recommendation,
                    "source": "service_boundary_analysis",
                    "reusability": reusability,
                },
                supporting_signals=[signal],
                estimated_effort=EffortEstimate.LARGE,
                risk_level=RiskLevel.MEDIUM,
                expected_impact=f"Extract {capability} as standalone service",
                capability_ids=[capability],
            )

            if action.is_traceable():
                actions.append(action)

        return actions

    def generate_from_duplicate_capabilities(
        self, duplicates: List[Dict[str, any]]
    ) -> List[RepoAction]:
        """Generate consolidate actions from cross-repo duplicates.

        Args:
            duplicates: List of duplicate capabilities across repos

        Returns:
            List of consolidate actions
        """
        actions = []

        for dup in duplicates:
            capability = dup.get("capability_name", "")
            repos = dup.get("repos", [])
            similarity = dup.get("similarity_score", 0.0)
            potential = dup.get("consolidation_potential", "")

            # Only consolidate if high similarity
            if similarity < 0.6 or self.repo_name not in repos:
                continue

            priority = calculate_action_priority(
                {"product_impact_score": similarity, "cross_repo_usage": len(repos)}
            )

            signal = SupportingSignal(
                signal_type="capability",
                signal_id=capability,
                description=f"Duplicated across {len(repos)} repos: {potential}",
                relevance=similarity,
            )

            action = RepoAction(
                action_id=str(uuid.uuid4())[:8],
                repo=self.repo_name,
                target=capability,
                action_type=ActionType.CONSOLIDATE,
                priority_score=priority,
                rationale={
                    "reason": potential,
                    "source": "cross_repo_analysis",
                    "similarity": similarity,
                    "duplicate_repos": repos,
                },
                supporting_signals=[signal],
                estimated_effort=EffortEstimate.LARGE,
                risk_level=RiskLevel.MEDIUM,
                expected_impact=f"Consolidate {capability} across {len(repos)} repos",
                capability_ids=[capability],
            )

            if action.is_traceable():
                actions.append(action)

        return actions

    def get_all_actions(self) -> List[RepoAction]:
        """Get all generated actions.

        Returns:
            List of all actions
        """
        return self.actions

    def add_actions(self, actions: List[RepoAction]):
        """Add actions to the generator.

        Args:
            actions: List of actions to add
        """
        # Only add traceable actions
        for action in actions:
            if action.is_traceable():
                self.actions.append(action)
