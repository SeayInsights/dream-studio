"""
Organization Intelligence - Enterprise Feature

Multi-repository analysis, executive dashboards, and organization-wide
insights are available in dream-studio-enterprise.

Features:
- Organization intelligence graphs
- VP Engineering metrics and dashboards
- CTO-level insights
- Engineering debt mapping
- Security and compliance views
- Cross-repo pattern detection
- Consolidation opportunity analysis
- Multi-project risk assessment

Learn more: https://dreamstudio.dev/enterprise
Contact: info@twinrootsllc.com
"""


class OrgIntelligenceNotAvailableError(Exception):
    """Raised when org intelligence is accessed without enterprise license."""

    pass


def check_org_intelligence_available():
    """Check if organization intelligence is available."""
    try:
        import dream_studio_enterprise.org_intelligence

        return True
    except ImportError:
        return False


def generate_org_intelligence(*args, **kwargs):
    """
    Generate organization intelligence graphs - Enterprise feature.

    This feature requires dream-studio-enterprise.
    Learn more: https://dreamstudio.dev/enterprise
    """
    if not check_org_intelligence_available():
        raise OrgIntelligenceNotAvailableError(
            "Organization intelligence requires dream-studio-enterprise. "
            "Learn more: https://dreamstudio.dev/enterprise or contact info@twinrootsllc.com"
        )
    from dream_studio_enterprise.org_intelligence import insight_engine

    return insight_engine.generate_insights(*args, **kwargs)


def build_org_graph(*args, **kwargs):
    """
    Build organization graph - Enterprise feature.

    This feature requires dream-studio-enterprise.
    Learn more: https://dreamstudio.dev/enterprise
    """
    if not check_org_intelligence_available():
        raise OrgIntelligenceNotAvailableError(
            "Organization graphs require dream-studio-enterprise. "
            "Learn more: https://dreamstudio.dev/enterprise or contact info@twinrootsllc.com"
        )
    from dream_studio_enterprise.org_intelligence import graph_builder

    return graph_builder.build_graph(*args, **kwargs)


def analyze_cross_repo(*args, **kwargs):
    """
    Analyze patterns across multiple repositories - Enterprise feature.

    This feature requires dream-studio-enterprise.
    Learn more: https://dreamstudio.dev/enterprise
    """
    if not check_org_intelligence_available():
        raise OrgIntelligenceNotAvailableError(
            "Cross-repo analysis requires dream-studio-enterprise. "
            "Learn more: https://dreamstudio.dev/enterprise or contact info@twinrootsllc.com"
        )
    from dream_studio_enterprise.org_intelligence import cross_repo_analyzer

    return cross_repo_analyzer.analyze_cross_repo_patterns(*args, **kwargs)


def generate_vp_metrics(*args, **kwargs):
    """
    Generate VP Engineering metrics - Enterprise feature.

    This feature requires dream-studio-enterprise.
    Learn more: https://dreamstudio.dev/enterprise
    """
    if not check_org_intelligence_available():
        raise OrgIntelligenceNotAvailableError(
            "VP metrics require dream-studio-enterprise. "
            "Learn more: https://dreamstudio.dev/enterprise or contact info@twinrootsllc.com"
        )
    from dream_studio_enterprise.org_intelligence import insight_engine

    return insight_engine.generate_vp_metrics(*args, **kwargs)


# Export stubs
__all__ = [
    "OrgIntelligenceNotAvailableError",
    "check_org_intelligence_available",
    "generate_org_intelligence",
    "build_org_graph",
    "analyze_cross_repo",
    "generate_vp_metrics",
]
