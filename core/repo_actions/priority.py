"""Priority scoring engine using strict weighted formula."""

from __future__ import annotations
from typing import Dict

# STRICT PRIORITY WEIGHTS (DO NOT MODIFY)
PRIORITY_WEIGHTS = {
    "risk": 0.40,  # 40% - from audit system
    "centrality": 0.25,  # 25% - dependency graph
    "usage": 0.25,  # 25% - runtime frequency
    "product_impact": 0.10,  # 10% - PRD value
}


def calculate_priority_score(
    risk_score: float, centrality_score: float, usage_score: float, product_impact_score: float
) -> float:
    """Calculate priority score using strict weighted formula.

    All inputs must be normalized to 0.0-1.0 range.

    Args:
        risk_score: From audit system (0.0-1.0)
        centrality_score: From dependency graph (0.0-1.0)
        usage_score: From event/decision frequency (0.0-1.0)
        product_impact_score: From PRD value ranking (0.0-1.0)

    Returns:
        Priority score (0.0-1.0)
    """
    score = (
        PRIORITY_WEIGHTS["risk"] * risk_score
        + PRIORITY_WEIGHTS["centrality"] * centrality_score
        + PRIORITY_WEIGHTS["usage"] * usage_score
        + PRIORITY_WEIGHTS["product_impact"] * product_impact_score
    )

    return min(1.0, max(0.0, score))


def normalize_risk_score(audit_risk: float) -> float:
    """Normalize audit risk score to 0.0-1.0.

    Args:
        audit_risk: Audit system risk score (0.0-1.0)

    Returns:
        Normalized risk score
    """
    # Audit risk is already 0.0-1.0, just pass through
    return min(1.0, max(0.0, audit_risk))


def normalize_centrality_score(coupling_score: int, max_coupling: int = 100) -> float:
    """Normalize centrality score to 0.0-1.0.

    Args:
        coupling_score: Coupling degree from dependency graph
        max_coupling: Maximum expected coupling (for normalization)

    Returns:
        Normalized centrality score
    """
    # Higher coupling = higher priority
    return min(1.0, coupling_score / max_coupling)


def normalize_usage_score(
    event_count: int, decision_count: int, max_events: int = 1000, max_decisions: int = 100
) -> float:
    """Normalize usage score to 0.0-1.0.

    Args:
        event_count: Number of events from this subsystem
        decision_count: Number of decisions from this subsystem
        max_events: Maximum expected events (for normalization)
        max_decisions: Maximum expected decisions (for normalization)

    Returns:
        Normalized usage score
    """
    event_norm = min(1.0, event_count / max_events)
    decision_norm = min(1.0, decision_count / max_decisions)

    # Average of both signals
    return (event_norm + decision_norm) / 2.0


def normalize_product_impact_score(reusability: float, cross_repo_usage: int = 0) -> float:
    """Normalize product impact score to 0.0-1.0.

    Args:
        reusability: Reusability score from capability graph (0.0-1.0)
        cross_repo_usage: Number of repos using this capability

    Returns:
        Normalized product impact score
    """
    # Reusability is already 0.0-1.0
    reuse_score = reusability

    # Cross-repo bonus (up to +0.2 for 3+ repos)
    cross_repo_bonus = min(0.2, cross_repo_usage * 0.1)

    return min(1.0, reuse_score + cross_repo_bonus)


def calculate_action_priority(signals: Dict[str, any]) -> float:
    """Calculate priority for an action from available signals.

    Args:
        signals: Dict with keys:
            - "risk_score" (float, optional)
            - "coupling_score" (int, optional)
            - "event_count" (int, optional)
            - "decision_count" (int, optional)
            - "reusability" (float, optional)
            - "cross_repo_usage" (int, optional)
            - "orphan_decision_count" (int, optional)
            - "missing_instrumentation_count" (int, optional)

    Returns:
        Priority score (0.0-1.0)
    """
    # Extract and normalize components
    risk_score = normalize_risk_score(signals.get("risk_score", 0.0))

    # Add bonus for orphan decisions/missing instrumentation
    orphan_count = signals.get("orphan_decision_count", 0)
    missing_count = signals.get("missing_instrumentation_count", 0)
    risk_bonus = min(0.3, (orphan_count + missing_count) * 0.1)
    risk_score = min(1.0, risk_score + risk_bonus)

    centrality_score = normalize_centrality_score(signals.get("coupling_score", 0))

    usage_score = normalize_usage_score(
        signals.get("event_count", 0), signals.get("decision_count", 0)
    )

    product_impact_score = normalize_product_impact_score(
        signals.get("reusability", 0.0), signals.get("cross_repo_usage", 0)
    )

    return calculate_priority_score(risk_score, centrality_score, usage_score, product_impact_score)
