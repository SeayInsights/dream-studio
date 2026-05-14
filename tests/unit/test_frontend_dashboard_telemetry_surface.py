from __future__ import annotations

from pathlib import Path

DASHBOARD = Path(__file__).resolve().parents[2] / "projections" / "frontend" / "dashboard.html"


def _html() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


def test_dashboard_contains_telemetry_surface_containers() -> None:
    html = _html()

    for marker in (
        'id="telemetry-traceability-section"',
        'id="telemetry-events-count"',
        'id="telemetry-human-loop-list"',
        'id="telemetry-attention-list"',
        'id="telemetry-component-list"',
        'id="telemetry-drilldown-list"',
        'id="telemetry-drilldown-detail"',
        'id="telemetry-module-list"',
        'id="telemetry-authority-metadata"',
        'id="telemetry-freshness-panel"',
        'id="telemetry-freshness-list"',
        'id="telemetry-backfill-status"',
        'id="telemetry-db-status"',
        'id="telemetry-operations-intelligence"',
        'id="telemetry-route-approval-rollup"',
        'id="telemetry-token-cost-rollup"',
        'id="telemetry-validation-security-rollup"',
        'id="telemetry-research-artifact-rollup"',
        'id="telemetry-release-readiness-rollup"',
        'id="telemetry-authority-state-rollup"',
        'id="shared-intelligence-section"',
        'id="shared-intelligence-status"',
        'id="shared-intelligence-warning"',
        'id="shared-learning-list"',
        'id="shared-hardening-list"',
        'id="shared-adapter-projection-list"',
        'id="shared-adapter-staleness-list"',
        'id="shared-context-packet-summary"',
        'id="shared-capability-route-list"',
        'id="shared-model-provider-list"',
        'id="shared-authority-metadata"',
    ):
        assert marker in html


def test_dashboard_fetches_required_telemetry_routes() -> None:
    html = _html()

    assert "const TELEMETRY_API_BASE = '/api/telemetry';" in html
    for route in ("/summary", "/attention", "/components", "/modules", "/status"):
        assert f"fetchTelemetry('{route}')" in html
    for drilldown in (
        "/api/telemetry/projects",
        "/api/telemetry/milestones/{milestone_id}",
        "/api/telemetry/tasks/{task_id}",
        "/api/telemetry/process-runs/{process_run_id}",
        "/api/telemetry/components/{component_type}/{component_id}",
    ):
        assert drilldown in html
    assert "summary?.drilldown_entry_points" in html
    assert "item.api_path" in html
    assert "telemetry-drilldown-button" in html
    assert "fetchTelemetryPath(path)" in html
    assert "renderTelemetryDrilldownDetail(path, detail)" in html
    assert "renderTelemetryFreshness(status)" in html
    assert "renderTelemetryOperationsIntelligence(summary, attention, components, status)" in html


def test_dashboard_fetches_shared_intelligence_authority_routes() -> None:
    html = _html()

    assert "const SHARED_INTELLIGENCE_API_BASE = '/api/shared-intelligence';" in html
    for route in (
        "/status?project_id=dream-studio",
        "/learning-dashboard?project_id=dream-studio",
        "/adapters/projections?project_id=dream-studio",
        "/adapters/staleness?project_id=dream-studio",
        "/context-packets/codex?project_id=dream-studio&packet_type=resume&limit=5",
        "/capability-routes?project_id=dream-studio",
        "/capability-routes/recommendation?project_id=dream-studio&task_class=code&required_capabilities=code,tool_use&risk_level=medium",
        "/model-providers",
        "/model-providers/capability-matrix?required_capabilities=code",
    ):
        assert f"fetchSharedIntelligence('{route}')" in html
    assert "initSharedIntelligenceSurface()" in html
    assert "renderSharedLearningDashboard(learning)" in html
    assert "renderSharedAdapterSurface(projections, staleness)" in html
    assert "renderSharedContextPacket(contextPacket)" in html
    assert "renderSharedCapabilityRoutes(capabilityRoutes, capabilityRecommendation)" in html
    assert "renderSharedModelProviders(modelProviders, capabilityMatrix)" in html


def test_dashboard_preserves_legacy_routes_and_non_blocking_telemetry_errors() -> None:
    html = _html()

    assert "const API_BASE = '/api/v1/metrics';" in html
    assert "fetch('/api/v1/security/findings?limit=50')" in html
    assert "fetch('/api/v1/analytics/anomalies')" in html
    assert "Telemetry routes are unavailable. Legacy dashboard sections remain active." in html
    assert (
        "Shared intelligence routes are unavailable. Telemetry and legacy dashboard sections remain active."
        in html
    )
    assert "Sparse data is expected during temp-DB smoke runs" in html
    assert "Freshness metadata unavailable; legacy dashboard sections remain active." in html
    assert "Backfill status:" in html
    assert "No human-loop items in this telemetry snapshot." in html
    assert "No component usage recorded for this snapshot." in html
    assert "Telemetry fetch failed" in html
    assert "initTelemetrySurface()" in html
    assert "attention?.grouped_items" in html
    assert "item(s)" in html
    assert "renderTelemetryHumanLoopQueue(attention" in html
    assert "prompt_required_items" in html
    assert "approval_required_items" in html
    assert "Dashboard is a derived view; resolve through source authority refs." in html
    assert "Shared intelligence fetch failed" in html
    assert "No learning events recorded for this snapshot." in html
    assert "No hardening candidates awaiting review." in html
    assert "No capability route recommendations recorded for this snapshot." in html
    assert "Context packet preview unavailable." in html


def test_dashboard_preserves_authority_metadata_without_hardcoded_operator_path() -> None:
    html = _html()

    assert 'data-derived-view="true"' in html
    assert 'data-primary-authority="false"' in html
    assert 'data-routing-authority="false"' in html
    assert "derived_view=" in html
    assert "primary_authority=" in html
    assert "routing_authority=" in html
    assert "C:\\Users\\Example User" not in html


def test_dashboard_modernization_preserves_legacy_behavior_with_professional_controls() -> None:
    html = _html()

    assert "Dream Studio Control Plane" in html
    assert 'class="nav-mark"' in html
    for stale_marker in (
        "📊 Overview",
        "🤖 Performance",
        "💰 Resources",
        "📁 Projects",
        "🧠 Intelligence",
        "🔄 In Progress:",
        "🚫 Blocked:",
    ):
        assert stale_marker not in html
    assert "Route & Approval Boundaries" in html
    assert "Dashboard is a derived view; resolve through source authority refs." in html
    assert "project-stack-evidence" in html
    assert "dependency-source-status" in html
    assert "graph-source-status" in html
    assert "Confirmed Stack Evidence" in html
    assert "Confirmed Dependency Summary" in html
    assert "No confirmed dependencies found" in html
    assert "Security Findings" in html
    assert "Attention Items" in html
    assert "health_model" in html
    assert "security_package_status" in html
    assert "work_order_status" in html
    assert "navigate('prd')" not in html
    assert 'data-retired-nav="knowledge-graph"' in html
    assert "The dashboard does not draw inferred or placeholder edges." in html
    assert "fetch('/api/v1/alerts/history')" in html
    assert "stats?.trend_last_30_days" in html
    assert "buildLearningEmptyState()" in html
    assert "Learning analytics have no current authority rows yet." in html
    assert "Math.random" not in html
    assert "function updateProjectModalAvailability(availableSurfaces)" in html
    assert "modal-bugs-card" in html
    assert "modal-violations-card" in html
    assert "availableSurfaces.health_trend" in html


def test_dashboard_escapes_telemetry_api_text_before_inner_html_rendering() -> None:
    html = _html()

    assert "function telemetryEscapeHtml(value)" in html
    assert "'&': '&amp;'" in html
    assert "telemetryEscapeHtml(item.example_title" in html
    assert "telemetryEscapeHtml(item.title" in html
    assert "telemetryEscapeHtml(item.attention_type" in html
    assert "telemetryEscapeHtml(module.module_name" in html
    assert "telemetryEscapeHtml(route)" in html
