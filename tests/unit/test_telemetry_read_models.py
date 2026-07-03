from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.event_store.studio_db import _connect
from core.telemetry.execution_spine import (
    record_dashboard_attention,
    record_execution_event,
    record_invocation,
    record_security_finding,
)

# record_process_run + record_route_decision retired migration 131 (process_runs and
# route_decision_records dropped; both writers were dead). Read-models now derive
# process-run drilldowns from execution_events.process_run_id, and route_status /
# route_explainability return empty. Tests seed process_run_id via the execution_event
# scope and no longer assert on route_decision rollups.
from core.telemetry.read_models import (
    dashboard_attention_summary,
    dashboard_module_read_models,
    dashboard_module_segments,
    global_telemetry_summary,
    component_usage_summary,
    milestone_telemetry_summary,
    process_run_timeline,
    project_telemetry_summary,
    task_telemetry_summary,
    workflow_execution_graph,
)


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "telemetry-read-models.db"
    conn = _connect(path)
    conn.close()
    return path


def _isolate_analytics(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the DuckDB analytics store at an isolated tmp path (WO-DBA-DROP:
    record_token_usage/token_usage_records were removed migration 137 — token
    facts are seeded as canonical token.consumed events into events_fact, the
    same source the DuckDB token_usage_records view derives from)."""
    from core.analytics import duckdb_store

    analytics_db = tmp_path / "aggregate_metrics.db"
    monkeypatch.setattr(duckdb_store, "analytics_db_path", lambda: analytics_db)
    return analytics_db


def _seed_token_consumed_event(
    analytics_db: Path,
    *,
    event_id: str,
    project_id: str | None = None,
    milestone_id: str | None = None,
    task_id: str | None = None,
    agent_id: str | None = None,
    skill_id: str | None = None,
    workflow_id: str | None = None,
    hook_id: str | None = None,
    model_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    event_timestamp: str = "2026-07-03T00:00:00Z",
) -> None:
    from core.analytics import duckdb_store

    conn = duckdb_store.connect_analytics(analytics_db, read_only=False)
    try:
        duckdb_store.ensure_analytics_schema(conn)
        conn.execute(
            "INSERT INTO events_fact (event_id, event_type, event_timestamp, project_id,"
            " milestone_id, task_id, agent_id, skill_id, workflow_id, hook_id, model_id,"
            " input_tokens, output_tokens, payload)"
            " VALUES (?, 'token.consumed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                event_id,
                event_timestamp,
                project_id,
                milestone_id,
                task_id,
                agent_id,
                skill_id,
                workflow_id,
                hook_id,
                model_id,
                input_tokens,
                output_tokens,
                json.dumps({"cache_creation_input_tokens": cache_creation_input_tokens}),
            ],
        )
    finally:
        conn.close()


def _seed_read_model_dbs(db_path: Path, analytics_db: Path) -> None:
    scope = {
        "project_id": "dream-studio",
        "milestone_id": "dashboard_read_models_for_telemetry_spine",
        "task_id": "read-model-test",
        "process_run_id": "process-run-read-model-test",
    }
    with _connect(db_path) as conn:
        # process_runs dropped migration 131 — the read-model derives process runs from
        # execution_events.process_run_id (carried in `scope`), so no record_process_run.
        record_execution_event(
            conn,
            **scope,
            event_id="event-read-model-test",
            event_type="workflow.invocation_recorded",
            event_name="Read model validation",
            actor_type="system",
            actor_id="pytest",
            agent_id="codex",
            skill_id="ds-core",
            workflow_id="route-first",
            hook_id="preflight",
            tool_id="pytest",
            model_id="gpt",
            source_refs=["core/telemetry/read_models.py"],
            evidence_refs=["read_model_evidence.yaml"],
            outcome_status="passed",
        )
        # record_execution_event now spools only; insert directly so FK-constrained
        # tables (agent_invocations etc.) can reference this event_id.
        conn.execute(
            """
            INSERT OR IGNORE INTO execution_events (
                event_id, event_type, event_name, project_id, milestone_id, task_id,
                process_run_id, actor_type, actor_id, agent_id, skill_id, workflow_id,
                hook_id, tool_id, model_id, source_refs_json, evidence_refs_json, outcome_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "event-read-model-test",
                "workflow.invocation_recorded",
                "Read model validation",
                scope["project_id"],
                scope["milestone_id"],
                scope["task_id"],
                scope["process_run_id"],
                "system",
                "pytest",
                "codex",
                "ds-core",
                "route-first",
                "preflight",
                "pytest",
                "gpt",
                '["core/telemetry/read_models.py"]',
                '["read_model_evidence.yaml"]',
                "passed",
            ),
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
                event_id="event-read-model-test",
                invocation_id=f"{invocation_type}-read-model-test",
                **{f"{invocation_type}_id": component_id},
                status="completed",
                purpose="read model validation",
                prevented_risky_action=(invocation_type == "hook"),
            )
        record_security_finding(
            conn,
            **scope,
            finding_id="security-read-model-test",
            scan_id="scan-read-model-test",
            severity="high",
            category="test",
            rule_id="DS-READMODEL-001",
            file_path="core/telemetry/read_models.py",
            start_line=1,
            end_line=1,
            description="Synthetic read-model validation finding.",
            recommendation="Confirm file/line rollup works.",
            status="open",
            introduced_by_agent_id="codex",
            introduced_by_skill_id="ds-quality",
            introduced_by_workflow_id="security-review",
            introduced_by_hook_id="preflight",
            evidence_refs=["read_model_evidence.yaml"],
        )
        conn.execute(
            """
            INSERT INTO validation_results (
                validation_id, project_id, milestone_id, task_id, process_run_id,
                event_id, validation_type, status, command, scope, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "validation-read-model-test",
                scope["project_id"],
                scope["milestone_id"],
                scope["task_id"],
                scope["process_run_id"],
                "event-read-model-test",
                "focused_test",
                "passed",
                "python -m pytest tests/unit/test_telemetry_read_models.py -q --tb=line",
                "telemetry read models",
                "Focused read model validation passed.",
            ),
        )
        conn.execute(
            """
            INSERT INTO research_evidence_records (
                research_id, project_id, milestone_id, task_id, process_run_id,
                event_id, question, decision_class, confidence, sources_json,
                source_summary, decision_impact, operator_verification_required
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "research-read-model-test",
                scope["project_id"],
                scope["milestone_id"],
                scope["task_id"],
                scope["process_run_id"],
                "event-read-model-test",
                "Can dashboard read models stay derived?",
                "no_research_needed",
                "high",
                '["file-backed authority"]',
                "Local source inspection was sufficient.",
                "continue_internal",
                0,
            ),
        )
        conn.execute(
            """
            INSERT INTO decision_records (
                decision_id, project_id, milestone_id, task_id, process_run_id,
                event_id, decision_type, decision_status, selected_option, rationale
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "decision-read-model-test",
                scope["project_id"],
                scope["milestone_id"],
                scope["task_id"],
                scope["process_run_id"],
                "event-read-model-test",
                "dashboard.authority",
                "recorded",
                "derived_view",
                "Dashboard read models are not primary authority.",
            ),
        )
        # record_blocker_resolution removed: blocker_resolution_records dropped migration 130
        # INSERT INTO artifact_records removed: artifact_records dropped migration 130
        conn.execute(
            """
            INSERT INTO outcome_records (
                outcome_id, project_id, milestone_id, task_id, process_run_id,
                event_id, outcome_type, outcome_status, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "outcome-read-model-test",
                scope["project_id"],
                scope["milestone_id"],
                scope["task_id"],
                scope["process_run_id"],
                "event-read-model-test",
                "validation",
                "passed",
                "Read model validation passed.",
            ),
        )
        # route_decision_records dropped migration 131 — no record_route_decision; the
        # global summary's route_status / route_explainability now return empty.
        record_dashboard_attention(
            conn,
            **scope,
            event_id="event-read-model-test",
            attention_id="attention-read-model-test",
            attention_type="security_finding",
            severity="warning",
            title="Synthetic dashboard attention item",
            summary="Attention rollup should remain dashboard-ready.",
            action_required=True,
            operator_action_required=False,
            prompt_required=False,
            source_refs=["tests/unit/test_telemetry_read_models.py"],
            evidence_refs=["read_model_evidence.yaml"],
        )
        conn.commit()

    # record_token_usage/token_usage_records removed (WO-DBA-DROP, migration
    # 137) — seed the equivalent canonical token.consumed event into the
    # DuckDB events_fact that the token_usage_records view derives from.
    # input_tokens + output_tokens = 225 to match the retired call's total
    # (120 input + 80 output + 25 cached — the new view's total_tokens is
    # input+output only, so the split changes but the total is preserved).
    # model is a real Claude model (not "gpt") so the DuckDB view's
    # token_model_pricing join produces a non-NULL, non-zero estimated_cost.
    _seed_token_consumed_event(
        analytics_db,
        event_id="token-read-model-test",
        project_id=scope["project_id"],
        milestone_id=scope["milestone_id"],
        task_id=scope["task_id"],
        agent_id="codex",
        skill_id="ds-core",
        workflow_id="route-first",
        hook_id="preflight",
        model_id="claude-sonnet-4-6",
        input_tokens=150,
        output_tokens=75,
        cache_creation_input_tokens=25,
    )


def test_dashboard_module_read_models_are_derived_views() -> None:
    modules = dashboard_module_read_models()
    module_ids = {module["module_id"] for module in modules}

    assert "route_milestone_analytics" in module_ids
    assert "security_analytics" in module_ids
    assert "token_analytics" in module_ids
    assert "tool_analytics" in module_ids
    for module in modules:
        assert module["source_tables"]
        assert module["dashboard_cards"]
        assert module["drilldown_paths"]
        assert module["empty_state"]
        assert module["derived_view"] is True
        assert module["primary_authority"] is False


def test_dashboard_module_segments_support_independent_views() -> None:
    segments = dashboard_module_segments()
    security = dashboard_module_segments("security_only")
    components = dashboard_module_segments("component_only")

    assert "security_only" in segments["segments"]
    assert security["active_segment"] == "security_only"
    assert [module["module_id"] for module in security["modules"]] == ["security_analytics"]
    assert {module["module_id"] for module in components["modules"]} >= {
        "agent_analytics",
        "skill_analytics",
        "workflow_analytics",
        "hook_analytics",
        "tool_analytics",
    }
    assert security["derived_view"] is True
    assert security["primary_authority"] is False


def test_global_summary_reads_telemetry_spine_and_marks_derived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = _db(tmp_path)
    _seed_read_model_dbs(db_path, _isolate_analytics(monkeypatch, tmp_path))

    summary = global_telemetry_summary(db_path)

    assert summary["derived_view"] is True
    assert summary["primary_authority"] is False
    assert "execution_events" in summary["source_tables"]
    assert summary["entity_counts"]["projects"] == 1
    assert summary["component_usage"]["agent"][0]["component_id"] == "codex"
    assert summary["component_usage"]["skill"][0]["component_id"] == "ds-core"
    assert summary["component_usage"]["workflow"][0]["component_id"] == "route-first"
    assert summary["component_usage"]["hook"][0]["component_id"] == "preflight"
    assert summary["component_usage"]["tool"][0]["component_id"] == "pytest"
    assert summary["token_usage"][0]["total_tokens"] == 225
    # WO-DBA-DROP: canonical token.consumed events carry no provider field
    # (the DuckDB view's provider column is always NULL); the honest default
    # replaces the old write-time _provider_from_model("gpt") inference.
    assert (
        summary["token_cost_intelligence"]["by_model_provider_component"][0]["provider"]
        == "unknown"
    )
    assert (
        summary["token_cost_intelligence"]["by_model_provider_component"][0][
            "reportable_cost_per_1k_tokens"
        ]
        > 0
    )
    assert summary["token_cost_intelligence"]["retry_patterns"]["available"] is False
    assert summary["findings"][0]["file_path"] == "core/telemetry/read_models.py"
    assert (
        summary["security_remediation_intelligence"]["remediation_candidates"][0]["severity"]
        == "high"
    )
    assert (
        summary["security_remediation_intelligence"]["remediation_policy"]["execution_authorized"]
        is False
    )
    assert summary["security_remediation_intelligence"]["attribution"][0]["agent_id"] == "unknown"
    assert summary["validation_outcomes"][0]["status"] == "passed"
    assert (
        summary["validation_outcome_intelligence"]["correlations"][0]["security_finding_count"] == 1
    )
    assert summary["validation_outcome_intelligence"]["correlations"][0]["token_total"] == 225
    assert summary["validation_outcome_intelligence"]["policy"]["primary_authority"] is False
    assert summary["research_decisions"]["research"][0]["decision_class"] == "no_research_needed"
    assert summary["research_decisions"]["decisions"][0]["selected_option"] == "derived_view"
    # research_blocker_resolution removed: blocker_resolution_records dropped migration 130
    # artifact_lineage_lifecycle removed: artifact_records dropped migration 130
    assert summary["dashboard_attention"][0]["prompt_required"] == 0
    # route_status / route_explainability dropped migration 131 (route_decision_records gone);
    # both now return empty lists.
    assert summary["route_status"] == []
    assert summary["route_explainability"] == []
    assert (
        summary["drilldown_entry_points"]["projects"][0]["api_path"]
        == "/api/telemetry/projects/dream-studio"
    )
    assert (
        summary["drilldown_entry_points"]["milestones"][0]["api_path"]
        == "/api/telemetry/milestones/dashboard_read_models_for_telemetry_spine?project_id=dream-studio"
    )
    assert (
        summary["drilldown_entry_points"]["tasks"][0]["api_path"]
        == "/api/telemetry/tasks/read-model-test?project_id=dream-studio&milestone_id=dashboard_read_models_for_telemetry_spine"
    )
    assert (
        summary["drilldown_entry_points"]["process_runs"][0]["api_path"]
        == "/api/telemetry/process-runs/process-run-read-model-test"
    )
    assert summary["drilldown_entry_points"]["components"][0]["api_path"].startswith(
        "/api/telemetry/components/"
    )


def test_project_milestone_task_and_process_drilldowns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = _db(tmp_path)
    _seed_read_model_dbs(db_path, _isolate_analytics(monkeypatch, tmp_path))

    project = project_telemetry_summary("dream-studio", db_path)
    milestone = milestone_telemetry_summary(
        "dashboard_read_models_for_telemetry_spine",
        project_id="dream-studio",
        db_path=db_path,
    )
    task = task_telemetry_summary(
        "read-model-test",
        project_id="dream-studio",
        milestone_id="dashboard_read_models_for_telemetry_spine",
        db_path=db_path,
    )
    timeline = process_run_timeline("process-run-read-model-test", db_path)

    assert project["entity_counts"]["events"] == 1
    assert milestone["component_usage"]["tool"][0]["component_id"] == "pytest"
    assert task["tokens"][0]["model_id"] == "claude-sonnet-4-6"
    assert timeline["process_run"]["process_run_id"] == "process-run-read-model-test"
    assert timeline["events"][0]["event_id"] == "event-read-model-test"
    assert timeline["invocations"]["agent"][0]["agent_id"] == "codex"
    assert timeline["validations"][0]["validation_id"] == "validation-read-model-test"
    assert timeline["findings"][0]["start_line"] == 1
    assert timeline["research"][0]["research_id"] == "research-read-model-test"
    assert timeline["decisions"][0]["decision_id"] == "decision-read-model-test"
    # timeline["blockers"] removed: blocker_resolution_records dropped migration 130
    assert timeline["attention"][0]["attention_id"] == "attention-read-model-test"


def test_workflow_execution_graph_links_process_events_validations_and_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _db(tmp_path)
    _seed_read_model_dbs(db_path, _isolate_analytics(monkeypatch, tmp_path))

    graph = workflow_execution_graph("route-first", db_path)

    assert graph["derived_view"] is True
    assert graph["primary_authority"] is False
    assert graph["workflow_id"] == "route-first"
    assert graph["invocations"][0]["workflow_id"] == "route-first"
    assert {node["node_type"] for node in graph["nodes"]} >= {
        "workflow",
        "process_run",
        "execution_event",
    }
    assert any(edge["relationship"] == "observed_in_process_run" for edge in graph["edges"])
    assert graph["process_runs"][0]["process_run_id"] == "process-run-read-model-test"
    assert graph["events"][0]["event_id"] == "event-read-model-test"
    assert graph["validations"][0]["validation_id"] == "validation-read-model-test"
    assert graph["outcomes"][0]["outcome_id"] == "outcome-read-model-test"
    assert graph["tokens"][0]["workflow_id"] == "route-first"
    assert graph["node_metadata_gap"]["workflow_node_table_available"] is False


def test_component_usage_and_attention_rollups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = _db(tmp_path)
    _seed_read_model_dbs(db_path, _isolate_analytics(monkeypatch, tmp_path))
    with _connect(db_path) as conn:
        record_dashboard_attention(
            conn,
            project_id="dream-studio",
            milestone_id="dashboard_read_models_for_telemetry_spine",
            task_id="read-model-test",
            process_run_id="process-run-read-model-test",
            event_id="event-read-model-test",
            attention_id="attention-read-model-test-duplicate",
            attention_type="security_finding",
            severity="warning",
            title="Synthetic dashboard attention item duplicate",
            summary="Duplicate attention facts should group for dashboard scanability.",
            action_required=True,
            operator_action_required=False,
            prompt_required=False,
            source_refs=["tests/unit/test_telemetry_read_models.py"],
            evidence_refs=["read_model_evidence.yaml"],
        )
        conn.commit()

    skill = component_usage_summary("skill", "ds-core", db_path)
    attention = dashboard_attention_summary(db_path, status="open")

    assert skill["usage"]["skill"]["rows"][0]["component_id"] == "ds-core"
    assert skill["tokens"][0]["skill_id"] == "ds-core"
    assert skill["hardening_intelligence"]["skill"][0]["component_id"] == "ds-core"
    assert skill["hardening_intelligence"]["skill"][0]["validation_count"] == 1
    assert skill["hardening_intelligence"]["skill"][0]["security_finding_count"] == 1
    assert skill["hardening_intelligence"]["skill"][0]["token_total"] == 225
    assert skill["hardening_intelligence"]["skill"][0]["primary_authority"] is False
    assert skill["derived_view"] is True
    assert attention["open_items"][0]["attention_id"] == "attention-read-model-test"
    assert attention["grouped_items"][0]["attention_type"] == "security_finding"
    assert attention["grouped_items"][0]["item_count"] == 2
    assert attention["grouped_items"][0]["example_title"]
    assert attention["prompt_required_items"] == []
    assert attention["warning_items"][0]["severity"] == "warning"
    assert attention["derived_view"] is True
    assert attention["primary_authority"] is False


def test_empty_state_for_missing_or_disabled_module_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = _db(tmp_path)
    # Isolate the DuckDB analytics store so this "empty" assertion doesn't
    # accidentally read a real local/CI aggregate_metrics.db.
    _isolate_analytics(monkeypatch, tmp_path)

    summary = global_telemetry_summary(db_path)
    project = project_telemetry_summary("missing-project", db_path)
    timeline = process_run_timeline("missing-process", db_path)

    assert summary["entity_counts"]["events"] == 0
    assert summary["component_usage"]["agent"] == []
    assert summary["token_usage"] == []
    assert summary["findings"] == []
    assert project["events"] == []
    assert project["component_usage"]["tool"] == []
    assert timeline["process_run"] is None
    assert timeline["events"] == []
    # timeline["blockers"] removed: blocker_resolution_records dropped migration 130
    assert timeline["tokens"] == []
    assert timeline["derived_view"] is True
    assert timeline["primary_authority"] is False


def test_security_remediation_intelligence_keeps_execution_approval_separate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _db(tmp_path)
    _seed_read_model_dbs(db_path, _isolate_analytics(monkeypatch, tmp_path))
    scope = {
        "project_id": "dream-studio",
        "milestone_id": "security_analytics_and_remediation_maturation",
        "task_id": "security-route-test",
        "process_run_id": "process-run-security-route-test",
    }
    with _connect(db_path) as conn:
        # process_runs dropped migration 131 — scope's process_run_id flows via the events below.
        record_security_finding(
            conn,
            **scope,
            finding_id="security-false-positive-test",
            scan_id="scan-security-route-test",
            severity="medium",
            category="security",
            rule_id="DS-FP-001",
            file_path="core/security/example.py",
            start_line=10,
            end_line=10,
            description="Synthetic false-positive finding.",
            recommendation="Document as false positive.",
            status="false_positive",
            introduced_by_agent_id="codex",
            introduced_by_skill_id="ds-quality",
            introduced_by_workflow_id="security-review",
            introduced_by_hook_id="post-validation",
            evidence_refs=["security_route_evidence.yaml"],
        )
        record_security_finding(
            conn,
            **scope,
            finding_id="security-resolved-test",
            scan_id="scan-security-route-test",
            severity="low",
            category="security",
            rule_id="DS-RESOLVED-001",
            file_path="core/security/example.py",
            start_line=22,
            end_line=22,
            description="Synthetic resolved finding.",
            recommendation="No further remediation required.",
            status="resolved",
            introduced_by_agent_id="codex",
            introduced_by_skill_id="ds-quality",
            introduced_by_workflow_id="security-review",
            introduced_by_hook_id="post-validation",
            evidence_refs=["security_route_evidence.yaml"],
        )
        conn.commit()

    project = project_telemetry_summary("dream-studio", db_path)
    intelligence = project["security_remediation_intelligence"]

    assert intelligence["remediation_policy"]["requires_future_work_order"] is True
    assert intelligence["remediation_policy"]["execution_authorized"] is False
    assert (
        intelligence["remediation_candidates"][0]["candidate_type"]
        == "security_remediation_work_order_candidate"
    )
    assert intelligence["remediation_candidates"][0]["requires_future_approval"] is True
    assert any(
        row["status"] == "false_positive" for row in intelligence["false_positive_candidates"]
    )
    assert any(row["status"] == "resolved" for row in intelligence["resolved_findings"])
    assert any(row["skill_id"] == "unknown" for row in intelligence["attribution"])


def test_validation_outcome_intelligence_correlates_failures_without_authorizing_fixes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _db(tmp_path)
    _seed_read_model_dbs(db_path, _isolate_analytics(monkeypatch, tmp_path))
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO validation_results (
                validation_id, project_id, milestone_id, task_id, process_run_id,
                event_id, validation_type, status, command, scope, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "validation-failed-correlation-test",
                "dream-studio",
                "dashboard_read_models_for_telemetry_spine",
                "read-model-test",
                "process-run-read-model-test",
                "event-read-model-test",
                "focused_test",
                "failed",
                "python -m pytest tests/unit/test_telemetry_read_models.py -q --tb=line",
                "telemetry read models",
                "Synthetic validation failure for correlation testing.",
            ),
        )
        conn.execute(
            """
            INSERT INTO outcome_records (
                outcome_id, project_id, milestone_id, task_id, process_run_id,
                event_id, outcome_type, outcome_status, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "outcome-failed-correlation-test",
                "dream-studio",
                "dashboard_read_models_for_telemetry_spine",
                "read-model-test",
                "process-run-read-model-test",
                "event-read-model-test",
                "validation",
                "failed",
                "Synthetic validation failure outcome.",
            ),
        )
        conn.commit()

    task = task_telemetry_summary(
        "read-model-test",
        project_id="dream-studio",
        milestone_id="dashboard_read_models_for_telemetry_spine",
        db_path=db_path,
    )
    intelligence = task["validation_outcome_intelligence"]

    assert (
        intelligence["failure_followup_candidates"][0]["candidate_type"]
        == "validation_failure_followup_candidate"
    )
    assert intelligence["failure_followup_candidates"][0]["requires_future_work_order"] is True
    assert intelligence["failure_followup_candidates"][0]["execution_authorized"] is False
    assert any(
        row["outcome_status"] == "failed" for row in intelligence["correlations"][0]["outcomes"]
    )
    assert intelligence["correlations"][0]["component_counts"]["tool"] == 1
    assert intelligence["policy"]["requires_future_work_order_for_fixes"] is True


def test_token_cost_intelligence_correlates_cost_with_outcomes_without_provider_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _db(tmp_path)
    analytics_db = _isolate_analytics(monkeypatch, tmp_path)
    _seed_read_model_dbs(db_path, analytics_db)
    scope = {
        "project_id": "dream-studio",
        "milestone_id": "token_cost_intelligence",
        "task_id": "token-cost-test",
        "process_run_id": "process-run-token-cost-test",
    }
    # record_token_usage/token_usage_records removed (WO-DBA-DROP, migration
    # 137) — seed the equivalent canonical token.consumed event. The DuckDB
    # view has no process_run_id dimension (canonical token.consumed events
    # carry no process_run_id), so outcome correlation falls back to matching
    # on project/milestone/task, which the seeded outcome_records row below
    # still satisfies. input_tokens + output_tokens = 1600 to match the
    # retired call's total (1000 + 500 + 100 cached — the new view's
    # total_tokens is input+output only).
    _seed_token_consumed_event(
        analytics_db,
        event_id="token-cost-intelligence-test",
        project_id=scope["project_id"],
        milestone_id=scope["milestone_id"],
        task_id=scope["task_id"],
        agent_id="codex",
        skill_id="ds-core",
        workflow_id="route-first",
        hook_id="preflight",
        model_id="gpt-5",
        input_tokens=1100,
        output_tokens=500,
        cache_creation_input_tokens=100,
    )
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO outcome_records (
                outcome_id, project_id, milestone_id, task_id, process_run_id,
                event_id, outcome_type, outcome_status, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "outcome-token-cost-test",
                scope["project_id"],
                scope["milestone_id"],
                scope["task_id"],
                scope["process_run_id"],
                None,
                "validation",
                "passed",
                "Synthetic token cost outcome.",
            ),
        )
        conn.commit()

    task = task_telemetry_summary(
        "token-cost-test",
        project_id="dream-studio",
        milestone_id="token_cost_intelligence",
        db_path=db_path,
    )
    intelligence = task["token_cost_intelligence"]

    assert intelligence["by_model_provider_component"][0]["model_id"] == "gpt-5"
    assert intelligence["by_model_provider_component"][0]["total_tokens"] == 1600
    assert intelligence["outcome_correlations"][0]["has_outcome_signal"] is True
    assert intelligence["outcome_correlations"][0]["outcomes"][0]["outcome_status"] == "passed"
    assert intelligence["policy"]["provider_billing_authority"] is False
    assert intelligence["retry_patterns"]["available"] is False


# test_artifact_lineage_lifecycle_flags_stale_and_superseded_without_cleanup_authority removed:
# artifact_records and blocker_resolution_records dropped in migration 130
# (aspirational telemetry, 0 rows in production, no live writers found in production code)
