"""Report formatters for action plans."""

from __future__ import annotations

from .model import RepoActionPlan, SystemPriorityMap, ActionType


def format_repo_action_plan(plan: RepoActionPlan) -> str:
    """Format repository action plan as markdown.

    Args:
        plan: Repository action plan

    Returns:
        Markdown formatted plan
    """
    lines = []
    lines.append(f"# Action Plan: {plan.repo_name}")
    lines.append("")
    lines.append(f"**Total Actions:** {len(plan.actions)}")
    lines.append(f"**High Priority:** {plan.high_priority_count}")
    lines.append(f"**Estimated Effort:** {plan.total_estimated_effort}")
    lines.append("")

    # Top 10 Actions
    lines.append("## Top Priority Actions")
    lines.append("")

    for i, action in enumerate(plan.actions[:10], 1):
        lines.append(f"### {i}. [{action.action_type.value.upper()}] {action.target}")
        lines.append("")
        lines.append(f"**Priority:** {action.priority_score:.0%}")
        lines.append(f"**Effort:** {action.estimated_effort.value}")
        lines.append(f"**Risk:** {action.risk_level.value}")
        lines.append("")

        lines.append("**Rationale:**")
        for key, value in action.rationale.items():
            lines.append(f"- {key}: {value}")
        lines.append("")

        lines.append("**Supporting Signals:**")
        for signal in action.supporting_signals:
            lines.append(
                f"- {signal.signal_type}: {signal.description} (relevance: {signal.relevance:.0%})"
            )
        lines.append("")

        lines.append(f"**Expected Impact:** {action.expected_impact}")
        lines.append("")

        # Traceability
        lines.append("**Traceable To:**")
        if action.decision_ids:
            lines.append(f"- Decisions: {', '.join(action.decision_ids)}")
        if action.event_ids:
            lines.append(f"- Events: {', '.join(action.event_ids)}")
        if action.coverage_finding_ids:
            lines.append(f"- Coverage: {', '.join(action.coverage_finding_ids)}")
        if action.capability_ids:
            lines.append(f"- Capabilities: {', '.join(action.capability_ids)}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Actions by subsystem
    lines.append("## Actions by Subsystem")
    lines.append("")

    for subsystem, actions in sorted(plan.subsystem_grouping.items()):
        lines.append(f"### {subsystem}")
        lines.append("")
        lines.append(f"**Action Count:** {len(actions)}")
        lines.append("")

        for action in sorted(actions, key=lambda a: a.priority_score, reverse=True):
            lines.append(
                f"- [{action.action_type.value}] {action.target} (priority: {action.priority_score:.0%})"
            )

        lines.append("")

    # Summary by action type
    lines.append("## Summary by Action Type")
    lines.append("")

    action_counts = {}
    for action in plan.actions:
        action_type = action.action_type.value
        if action_type not in action_counts:
            action_counts[action_type] = 0
        action_counts[action_type] += 1

    for action_type, count in sorted(action_counts.items()):
        lines.append(f"- **{action_type}**: {count}")

    lines.append("")

    return "\n".join(lines)


def format_system_priority_map(system_map: SystemPriorityMap) -> str:
    """Format system-wide priority map as markdown.

    Args:
        system_map: System priority map

    Returns:
        Markdown formatted map
    """
    lines = []
    lines.append("# System-Wide Priority Map")
    lines.append("")
    lines.append(f"**Top Actions Across All Repositories:** {len(system_map.top_actions)}")
    lines.append("")

    # Top 10 actions
    lines.append("## Top 10 Highest Impact Actions")
    lines.append("")

    for i, action in enumerate(system_map.top_actions, 1):
        lines.append(f"### {i}. [{action.repo}] {action.target}")
        lines.append("")
        lines.append(f"**Type:** {action.action_type.value}")
        lines.append(f"**Priority:** {action.priority_score:.0%}")
        lines.append(f"**Effort:** {action.estimated_effort.value}")
        lines.append(f"**Risk:** {action.risk_level.value}")
        lines.append("")
        lines.append(f"**Reason:** {action.rationale.get('reason', 'N/A')}")
        lines.append(f"**Impact:** {action.expected_impact}")
        lines.append("")

    # By capability domain
    lines.append("## Actions by Capability Domain")
    lines.append("")

    for domain, actions in sorted(system_map.by_capability_domain.items()):
        lines.append(f"### {domain.title()} Domain")
        lines.append("")

        for action in sorted(actions, key=lambda a: a.priority_score, reverse=True):
            lines.append(
                f"- [{action.repo}] {action.action_type.value}: {action.target} (priority: {action.priority_score:.0%})"
            )

        lines.append("")

    # Dependency-ordered execution sequence
    lines.append("## Recommended Execution Sequence")
    lines.append("")
    lines.append("_Actions ordered by dependencies and priority_")
    lines.append("")

    for i, action in enumerate(system_map.dependency_ordered_actions, 1):
        lines.append(f"{i}. [{action.repo}] {action.action_type.value}: {action.target}")

    lines.append("")

    return "\n".join(lines)


def format_action_summary(plan: RepoActionPlan) -> str:
    """Format brief action summary.

    Args:
        plan: Repository action plan

    Returns:
        Brief summary text
    """
    lines = []
    lines.append(f"# {plan.repo_name} - Action Summary")
    lines.append("")
    lines.append(f"- **Total Actions:** {len(plan.actions)}")
    lines.append(f"- **High Priority:** {plan.high_priority_count}")
    lines.append(f"- **Effort:** {plan.total_estimated_effort}")
    lines.append("")

    # Top 3 actions
    lines.append("**Top 3 Actions:**")
    for i, action in enumerate(plan.actions[:3], 1):
        lines.append(
            f"{i}. {action.action_type.value}: {action.target} ({action.priority_score:.0%})"
        )

    return "\n".join(lines)
