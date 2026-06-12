from __future__ import annotations

from pathlib import Path

from core.decisions.emitter import emit_decision
from core.event_store.studio_db import _connect, archive_workflow
from core.research.store import save_research
from core.telemetry.emitters import (
    MODE_STRICT,
    TelemetryContext,
    emit_decision_record,
    emit_research_evidence_record,
    emit_workflow_invocation,
)


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "telemetry.db"
    conn = _connect(path)
    conn.close()
    return path


def test_workflow_invocation_emitter_is_idempotent_and_writes_attention(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    kwargs = {
        "workflow_id": "route-first-validation",
        "status": "completed_with_failures",
        "run_key": "run-workflow-test",
        "node_id": "validate",
        "yaml_path": "workflows/route-first-validation.yaml",
        "nodes": {"validate": {"status": "failed"}},
        "context": TelemetryContext(
            project_id="dream-studio",
            milestone_id="workflow_research_decision_telemetry_emitters",
            task_id="workflow-test",
            process_run_id="run-workflow-test",
            source_refs=("core/event_store/studio_db.py",),
            evidence_refs=("workflow_bridge_evidence.yaml",),
        ),
        "db_path": db_path,
        "mode": MODE_STRICT,
    }

    first = emit_workflow_invocation(**kwargs)
    second = emit_workflow_invocation(**kwargs)

    assert first.emitted is True
    assert second.emitted is False
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT workflow_id, outcome_status AS status FROM execution_events WHERE event_id = ? AND event_type = 'workflow.invocation_recorded'",
            (first.record_id,),
        ).fetchone()
        assert dict(row) == {"workflow_id": "route-first-validation", "status": "failed"}
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM execution_events WHERE event_type = 'workflow.invocation_recorded'"
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM dashboard_attention_items WHERE event_id = ? AND attention_type = 'workflow_status_attention'",
                (first.event_id,),
            ).fetchone()[0]
            == 1
        )
    finally:
        conn.close()


def test_archive_workflow_preserves_raw_tables_and_dual_writes(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    workflow = {
        "workflow": "daily-standup",
        "yaml_path": "workflows/daily-standup.yaml",
        "status": "success",
        "started": "2026-05-13T00:00:00+00:00",
        "finished": "2026-05-13T00:00:02+00:00",
        "nodes": {"summary": {"status": "completed", "output": "ok"}},
    }

    assert archive_workflow("run-archive-workflow-test", workflow, db_path=db_path) is True

    conn = _connect(db_path)
    try:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM raw_workflow_runs WHERE run_key = 'run-archive-workflow-test'"
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM raw_workflow_nodes WHERE run_key = 'run-archive-workflow-test'"
            ).fetchone()[0]
            == 1
        )
        row = conn.execute(
            "SELECT workflow_id, outcome_status AS status FROM execution_events WHERE event_type = 'workflow.invocation_recorded'"
        ).fetchone()
        assert row["workflow_id"] == "daily-standup"
        assert row["status"] == "completed"
    finally:
        conn.close()


def test_research_evidence_emitter_records_operator_verification_attention(tmp_path: Path) -> None:
    db_path = _db(tmp_path)

    result = emit_research_evidence_record(
        question="Should material-risk research route to operator verification?",
        decision_class="operator_verification_required",
        confidence="medium",
        sources=[{"url": "file://authority", "tier": "local"}],
        source_summary="Synthetic research requires operator verification.",
        decision_impact="dashboard_attention",
        operator_verification_required=True,
        context=TelemetryContext(project_id="dream-studio", task_id="research-test"),
        db_path=db_path,
        mode=MODE_STRICT,
    )

    assert result.emitted is True
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT question, confidence, operator_verification_required FROM research_evidence_records WHERE research_id = ?",
            (result.record_id,),
        ).fetchone()
        assert row["confidence"] == "medium"
        assert row["operator_verification_required"] == 1
        assert "material-risk" in row["question"]
        attention = conn.execute(
            "SELECT operator_action_required, prompt_required FROM dashboard_attention_items WHERE event_id = ?",
            (result.event_id,),
        ).fetchone()
        assert dict(attention) == {"operator_action_required": 1, "prompt_required": 0}
    finally:
        conn.close()


def test_file_backed_research_store_dual_writes_without_losing_file_output(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = _db(tmp_path)
    monkeypatch.setenv("DREAM_STUDIO_TELEMETRY_DB", str(db_path))
    monkeypatch.setattr("core.config.paths.user_data_dir", lambda: tmp_path / "user-data")

    path = save_research(
        "route first research",
        {
            "sources": [
                {"url": "file://stage-gates", "tier": "local", "key_findings": "route-first"}
            ],
            "confidence": "high",
            "findings": "Route-first evidence is local and sufficient.",
            "refresh_due": "2026-06-01",
            "saved_date": "2026-05-13",
        },
    )

    assert path.is_file()
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT question, confidence FROM research_evidence_records").fetchone()
        assert row["question"] == "route first research"
        assert row["confidence"] == "high"
    finally:
        conn.close()


def test_decision_emitter_records_attention_and_is_idempotent(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    kwargs = {
        "decision_type": "architecture.approval",
        "decision_status": "recorded",
        "selected_option": "require_operator_approval",
        "rationale": "Architecture direction requires operator review.",
        "options_considered": ["continue_internal", "require_operator_approval"],
        "route_impact": "operator_attention",
        "approval_required": True,
        "source_decision_id": "decision-approval-test",
        "context": TelemetryContext(project_id="dream-studio", task_id="decision-test"),
        "db_path": db_path,
        "mode": MODE_STRICT,
    }

    first = emit_decision_record(**kwargs)
    second = emit_decision_record(**kwargs)

    assert first.emitted is True
    assert second.emitted is False
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT decision_type, selected_option FROM decision_records WHERE decision_id = ?",
            (first.record_id,),
        ).fetchone()
        assert dict(row) == {
            "decision_type": "architecture.approval",
            "selected_option": "require_operator_approval",
        }
        attention = conn.execute(
            "SELECT operator_action_required, prompt_required FROM dashboard_attention_items WHERE event_id = ?",
            (first.event_id,),
        ).fetchone()
        assert dict(attention) == {"operator_action_required": 1, "prompt_required": 0}
    finally:
        conn.close()


def test_legacy_decision_log_dual_writes_telemetry(tmp_path: Path, monkeypatch) -> None:
    db_path = _db(tmp_path)
    monkeypatch.setenv("DREAM_STUDIO_TELEMETRY_DB", str(db_path))

    from core.config.database import DatabaseRuntime, initialize_database

    DatabaseRuntime.reset_instance()
    initialize_database(db_path)
    try:
        decision = emit_decision(
            decision_type="route.continue",
            context={"project_id": "dream-studio", "task_id": "decision-log-test"},
            outcome={"selected_option": "continue_internal", "route_impact": "continue"},
            reasoning={"rationale": "No stop gate exists."},
            confidence=0.95,
            policy_applied="route-first",
            source_subsystem="work_orders",
        )

        conn = _connect(db_path)
        try:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM decision_log WHERE decision_id = ?",
                    (decision.decision_id,),
                ).fetchone()[0]
                == 1
            )
            row = conn.execute(
                "SELECT decision_type, selected_option FROM decision_records WHERE decision_id = ?",
                (decision.decision_id,),
            ).fetchone()
            assert dict(row) == {
                "decision_type": "route.continue",
                "selected_option": "continue_internal",
            }
        finally:
            conn.close()
    finally:
        DatabaseRuntime.reset_instance()


def test_workflow_research_decision_emitters_best_effort_failure_does_not_raise(
    tmp_path: Path,
) -> None:
    empty_db = tmp_path / "empty.db"

    workflow = emit_workflow_invocation(workflow_id="wf", status="completed", db_path=empty_db)
    research = emit_research_evidence_record(question="q", db_path=empty_db)
    decision = emit_decision_record(decision_type="d", decision_status="recorded", db_path=empty_db)

    assert workflow.emitted is False
    assert workflow.error
    assert research.emitted is False
    assert research.error
    assert decision.emitted is False
    assert decision.error
