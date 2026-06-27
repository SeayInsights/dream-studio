from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.telemetry.execution_spine import (
    classify_research_blocker,
    dashboard_module_declarations,
    record_dashboard_attention,
    record_execution_event,
    record_invocation,
    record_process_run,
    record_research_evidence,
    record_route_decision,
    record_security_finding,
    record_token_usage,
    token_rollup,
)

REQUIRED_TABLES = {
    "execution_events",
    "process_runs",
    # agent_invocations, skill_invocations, workflow_invocations, hook_invocations,
    # tool_invocations: dropped in migration 106 (data covered by execution_events).
    "token_usage_records",
    # findings: dropped in migration 112 (data migrated to security_events + findings_current_status).
    "decision_records",
    "research_evidence_records",
    # blocker_resolution_records: dropped migration 130 (aspirational, 0 rows, no live writer)
    "validation_results",
    # artifact_records: dropped migration 130 (aspirational, 0 rows, no production writer)
    "outcome_records",
    "route_decision_records",
    "dashboard_attention_items",
    # authority_projection_records: dropped migration 130 (aspirational, 0 rows, no live writer)
}


def _seed(conn):
    scope = {
        "project_id": "dream-studio",
        "milestone_id": "execution_telemetry_traceability_spine",
        "task_id": "telemetry-spine-test",
        "process_run_id": "process-run-telemetry-test",
    }
    record_process_run(conn, **scope, run_type="validation", status="completed")
    record_execution_event(
        conn,
        **scope,
        event_id="event-telemetry-test",
        event_type="validation",
        event_name="Telemetry spine validation",
        actor_type="agent",
        actor_id="codex",
        agent_id="codex",
        skill_id="ds-core",
        workflow_id="route-first",
        hook_id="preflight",
        tool_id="pytest",
        model_id="gpt",
        adapter_id="codex-local",
        source_refs=["tests/unit/test_execution_telemetry_spine.py"],
        evidence_refs=["validation-evidence.yaml"],
        outcome_status="passed",
    )
    for invocation_type, component_id in (
        ("agent", "codex"),
        ("skill", "ds-core"),
        ("workflow", "route-first"),
        ("hook", "preflight"),
        ("tool", "pytest"),
    ):
        record_invocation(
            conn,
            invocation_type,
            **scope,
            event_id="event-telemetry-test",
            invocation_id=f"{invocation_type}-invocation-telemetry-test",
            **{f"{invocation_type}_id": component_id},
            status="completed",
            purpose="focused validation",
            prevented_risky_action=(invocation_type == "hook"),
        )
    record_token_usage(
        conn,
        **scope,
        token_usage_id="token-telemetry-test",
        agent_id="codex",
        skill_id="ds-core",
        workflow_id="route-first",
        hook_id="preflight",
        model_id="gpt",
        provider="openai",
        input_tokens=100,
        output_tokens=50,
        cached_tokens=25,
        estimated_cost=0.01,
        purpose="focused validation",
    )
    record_security_finding(
        conn,
        **scope,
        finding_id="security-finding-telemetry-test",
        scan_id="scan-telemetry-test",
        severity="medium",
        category="test",
        rule_id="DS-TEST-001",
        file_path="core/telemetry/execution_spine.py",
        start_line=1,
        end_line=1,
        description="Synthetic validation finding",
        recommendation="Confirm file/line attribution works",
        status="open",
        introduced_by_agent_id="codex",
        introduced_by_skill_id="ds-core",
        introduced_by_workflow_id="route-first",
        introduced_by_hook_id="preflight",
        evidence_refs=["validation-evidence.yaml"],
    )
    record_research_evidence(
        conn,
        **scope,
        event_id="event-telemetry-test",
        research_id="research-telemetry-test",
        question="Can local evidence resolve the blocker?",
        decision_class="concrete_research_resolved_continue",
        confidence="high",
        sources=["file-backed authority"],
        source_summary="Sufficient local evidence",
        decision_impact="continue",
    )
    record_route_decision(
        conn,
        **scope,
        event_id="event-telemetry-test",
        route_id="route-telemetry-test",
        route_decision="continue_internal_or_start_next_milestone",
        handoff_required=False,
        operator_action_required=False,
        prompt_required=False,
        next_stage_gate="structured_authority_projection",
        next_milestone="runtime_projection_update",
        recommended_next_work_order="none",
        source_refs=["docs/product/dream-studio-stage-gates.yaml"],
    )
    record_dashboard_attention(
        conn,
        **scope,
        event_id="event-telemetry-test",
        attention_id="attention-telemetry-test",
        attention_type="approval",
        severity="info",
        title="Synthetic dashboard approval item",
        summary="Material risks can route to dashboard attention without prompt when safe.",
        action_required=True,
        operator_action_required=True,
        prompt_required=False,
    )
    # record_authority_projection removed: authority_projection_records dropped migration 130
    conn.execute(
        """
        INSERT INTO decision_records (
            decision_id, project_id, milestone_id, task_id, process_run_id,
            event_id, decision_type, decision_status, selected_option, rationale
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "decision-telemetry-test",
            scope["project_id"],
            scope["milestone_id"],
            scope["task_id"],
            scope["process_run_id"],
            "event-telemetry-test",
            "operator_direction",
            "recorded",
            "route_first",
            "Preserve route-first continuation.",
        ),
    )
    conn.execute(
        """
        INSERT INTO validation_results (
            validation_id, project_id, milestone_id, task_id, process_run_id,
            event_id, validation_type, status, command, scope, summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "validation-telemetry-test",
            scope["project_id"],
            scope["milestone_id"],
            scope["task_id"],
            scope["process_run_id"],
            "event-telemetry-test",
            "focused_test",
            "passed",
            "python -m pytest tests/unit/test_execution_telemetry_spine.py -q --tb=line",
            "telemetry spine",
            "Focused telemetry spine validation passed.",
        ),
    )
    # artifact_records INSERT removed: table dropped in migration 130
    conn.execute(
        """
        INSERT INTO outcome_records (
            outcome_id, project_id, milestone_id, task_id, process_run_id,
            event_id, outcome_type, outcome_status, summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "outcome-telemetry-test",
            scope["project_id"],
            scope["milestone_id"],
            scope["task_id"],
            scope["process_run_id"],
            "event-telemetry-test",
            "validation",
            "passed",
            "Telemetry spine can write/read required facts.",
        ),
    )
    conn.commit()


def test_migration_creates_required_execution_telemetry_tables(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "telemetry.db")
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    finally:
        conn.close()

    assert tables >= REQUIRED_TABLES


def test_spine_writes_reads_and_global_analytics(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "telemetry.db")
    try:
        _seed(conn)

        assert conn.execute("SELECT COUNT(*) FROM execution_events").fetchone()[0] == 1
        # usage_by_component for invocation tables removed — migration 106 dropped
        # agent_invocations, skill_invocations, workflow_invocations, hook_invocations,
        # tool_invocations. Data is now in execution_events.
        assert token_rollup(conn)[0]["total_tokens"] == 175
        # findings_rollup reads findings_current_status which is a projection
        # (populated by FindingsProjection.fold_spine, not in direct DB tests).
        # Assert on security_events spine directly instead.
        row = conn.execute(
            "SELECT file_path, severity FROM security_events"
            " WHERE event_kind = 'finding.recorded'"
            " AND event_id = 'security-finding-telemetry-test'"
        ).fetchone()
        assert row is not None
        assert row[0] == "core/telemetry/execution_spine.py"
        assert row[1] == "medium"
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM route_decision_records WHERE handoff_required = 0"
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM dashboard_attention_items WHERE prompt_required = 0"
            ).fetchone()[0]
            == 1
        )
    finally:
        conn.close()


def test_dashboard_modules_declare_empty_states_and_drilldowns() -> None:
    modules = dashboard_module_declarations()

    assert len(modules) >= 9  # artifact_analytics module dropped migration 130
    for module in modules:
        assert module["source_tables"]
        assert module["dashboard_cards"]
        assert module["drilldown_paths"]
        assert module["empty_state"]


def test_research_blocker_routes() -> None:
    low_risk = classify_research_blocker(confidence="high", sources_sufficient=True)
    assert low_risk.route_class == "concrete_research_resolved_continue"
    assert low_risk.prompt_required is False
    assert low_risk.continue_allowed is True

    material = classify_research_blocker(
        confidence="high",
        sources_sufficient=True,
        material_risk_change=True,
        route_can_pause_or_route_around=True,
    )
    assert material.route_class == "concrete_research_requires_dashboard_approval"
    assert material.dashboard_approval_required is True
    assert material.prompt_required is False

    unknown = classify_research_blocker(confidence="low", sources_sufficient=False)
    assert unknown.route_class == "true_unknown_prompt_required"
    assert unknown.prompt_required is True


def test_docker_profile_docs_keep_core_local_first() -> None:
    doc = Path("docs/operations/docker-module-profiles.md").read_text(encoding="utf-8")

    assert "Docker is optional for Dream Studio core" in doc
    assert "core telemetry writes continue through local SQLite" in doc
    assert "does not start containers" in doc
