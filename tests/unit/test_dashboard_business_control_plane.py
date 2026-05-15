from __future__ import annotations

from pathlib import Path


DASHBOARD = Path(__file__).resolve().parents[2] / "projections" / "frontend" / "dashboard.html"


def _html() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


def _sidebar(html: str) -> str:
    start = html.index('<nav class="sidebar"')
    end = html.index("</nav>", start)
    return html[start:end]


def test_business_navigation_removes_alerts_from_sidebar() -> None:
    html = _html()
    sidebar = _sidebar(html)

    for section in ("Command", "Operations", "Governance", "Intelligence"):
        assert section in sidebar
    for item in ("Overview", "Projects", "Workflows", "Skills", "Hooks", "Models"):
        assert item in sidebar
    assert "Alerts" not in sidebar
    assert "navigate('alerts')" not in sidebar


def test_alert_bell_is_global_attention_entry_point() -> None:
    html = _html()

    assert 'id="alert-bell-button"' in html
    assert 'id="alert-bell-count"' in html
    assert 'id="alert-drawer"' in html
    assert 'data-component="AlertDrawer"' in html
    assert "approval_required" in html
    assert "validation_failures" in html
    assert "manual_review" in html
    assert "workflow_attention" in html


def test_reusable_component_and_view_model_contracts_are_named() -> None:
    html = _html()

    for component in (
        "DashboardShell",
        "SidebarNavigation",
        "TopBar",
        "AlertBell",
        "AlertDrawer",
        "PageStoryHeader",
        "BusinessStoryCard",
        "MetricCard",
        "ChartCard",
        "InterpretationCard",
        "EmptyState",
        "SourceConflictState",
        "DataFreshnessBadge",
        "DeveloperDiagnosticsDrawer",
        "DrilldownPanel",
        "GroupedTable",
        "StatusPill",
    ):
        assert component in html

    for view_model in (
        "DashboardStoryProjection",
        "OperatingLoopViewModel",
        "AttentionSummaryViewModel",
        "ProjectPortfolioViewModel",
        "SecurityPostureViewModel",
        "ModelUsageViewModel",
        "CapabilityReliabilityViewModel",
        "HookHealthViewModel",
        "WorkflowHealthViewModel",
        "AnomalyReliabilityViewModel",
        "LearningFlywheelViewModel",
        "InsightRecommendationViewModel",
    ):
        assert view_model in html


def test_major_pages_have_business_story_contracts() -> None:
    html = _html()

    for page_id in (
        "overview",
        "projects",
        "security",
        "models",
        "skills",
        "hooks",
        "workflows",
        "anomalies",
        "learning",
        "ml",
    ):
        assert f"{page_id}:" in html

    assert "DASHBOARD_PAGE_STORIES" in html
    assert 'data-page-story="${pageId}"' in html
    assert "What this means" in html
    assert "Why it matters" in html
    assert "What needs action" in html


def test_operating_loop_story_is_graph_led() -> None:
    html = _html()

    assert 'data-component="OperatingLoopViewModel"' in html
    for node in ("Goal", "Plan", "Route", "Execute", "Validate", "Evidence", "Gate", "Next Action"):
        assert node in html
    for status in ("complete", "in_progress", "needs_approval", "unavailable"):
        assert status in html


def test_default_business_copy_hides_raw_technical_source_labels() -> None:
    html = _html()

    assert "Dashboard output is derived. Use evidence and authority references" in html
    assert "Source confidence:" in html
    assert "From route authority records." in html
    assert "Source confidence: project dependency authority" in html
    assert "from current dependency authority" in html
    assert "From route_decision_records." not in html
    assert "source: /api/v1/projects/" not in html
    assert "confirmed edges from /api/discovery/internal/graph" not in html


def test_developer_diagnostics_gate_raw_markers() -> None:
    html = _html()

    assert 'data-component="DeveloperDiagnosticsDrawer"' in html
    assert "RAW_TECHNICAL_MARKERS" in html
    for raw_marker in ("/api/", "route_decision_records", "validation_results", "source_tables"):
        assert raw_marker in html


def test_empty_source_and_conflict_states_are_explicit() -> None:
    html = _html()

    for state in (
        "empty_but_valid",
        "unavailable_missing_projection",
        "unavailable_missing_source",
        "stale",
        "source_conflict",
        "manual_review_required",
        "blocked_by_policy",
    ):
        assert state in html
    assert "Project portfolio is loading. If no current authority rows exist" in html
    assert '<div class="text-center text-gray-500 py-8">Loading projects...</div>' not in html


def test_anomalies_and_learning_are_honest_about_sparse_data() -> None:
    html = _html()

    assert "No anomaly detected does not mean healthy; reliability risk exists" in html
    assert "synthetic trend lines stay disabled" in html
    assert "low sample sizes reduce confidence" in html
