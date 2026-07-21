from __future__ import annotations

from pathlib import Path

from control.analysis.bugs import _emit_security_bug_telemetry, _store_bugs
from core.event_store.studio_db import _connect
from core.telemetry.emitters import (
    MODE_STRICT,
    TelemetryContext,
    emit_security_finding,
    emit_validation_result,
)
from core.work_orders.evals import create_skill_identifier_safety_eval


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "telemetry.db"
    conn = _connect(path)
    conn.close()
    return path


def test_validation_result_emitter_writes_event_result_outcome_and_attention(
    tmp_path: Path,
) -> None:
    db_path = _db(tmp_path)

    result = emit_validation_result(
        validation_type="focused_pytest",
        status="failed",
        command="python -m pytest tests/unit/test_example.py -q --tb=line",
        scope="unit",
        summary="One focused validation failed.",
        pass_count=3,
        fail_count=1,
        context=TelemetryContext(
            project_id="dream-studio",
            milestone_id="validation_security_telemetry_emitters",
            task_id="validation-test",
            process_run_id="process-validation-test",
            source_refs=("tests/unit/test_validation_security_telemetry_emitters.py",),
            evidence_refs=("validation_evidence.yaml",),
        ),
        db_path=db_path,
        mode=MODE_STRICT,
    )

    assert result.emitted is True
    conn = _connect(db_path)
    try:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM execution_events WHERE event_id = ?",
                (result.event_id,),
            ).fetchone()[0]
            == 1
        )
        validation = conn.execute(
            "SELECT status, command FROM validation_results WHERE validation_id = ?",
            (result.record_id,),
        ).fetchone()
        assert validation["status"] == "failed"
        assert "pytest" in validation["command"]
        # outcome_records + dashboard_attention_items dropped migration 139
        # (WO-AI-SPINE, AD-5) — pure duplication of the execution_events row
        # this emitter already writes (outcome_status='failed' below is both
        # the outcome and the attention-worthy signal).
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM execution_events WHERE event_id = ? AND outcome_status = 'failed'",
                (result.event_id,),
            ).fetchone()[0]
            == 1
        )
    finally:
        conn.close()


def test_eval_artifact_path_dual_writes_validation_without_breaking_file_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = _db(tmp_path)
    monkeypatch.setenv("DREAM_STUDIO_TELEMETRY_DB", str(db_path))

    from core.work_orders.packet_store import get_packet_artifact

    artifact, path = create_skill_identifier_safety_eval(
        work_order={"work_order_id": "wo-telemetry-eval-test", "allowed_skills": ["ds-core"]},
        storage_root=tmp_path / "work-orders",
    )

    # WO-FILESDB-C3: the eval artifact is persisted to the packet store (kind='eval'),
    # not an on-disk file — path is None. The validation telemetry dual-write below is
    # the behavior under test and is unaffected.
    assert path is None
    assert (
        get_packet_artifact(
            "wo-telemetry-eval-test",
            "eval",
            instance_key="skill_identifier_safety",
            storage_root=tmp_path / "work-orders",
        )
        is not None
    )
    assert artifact["pass_fail"] == "pass"
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT validation_type, status FROM validation_results WHERE validation_type = ?",
            ("skill_identifier_safety",),
        ).fetchone()
        assert row["status"] == "passed"
        # outcome_records dropped migration 139 (WO-AI-SPINE, AD-5) — outcomes are
        # derived from execution_events.
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM execution_events WHERE event_type = 'validation.result_recorded'"
            ).fetchone()[0]
            == 1
        )
    finally:
        conn.close()


def test_security_finding_emitter_is_idempotent_and_records_file_line_attention(
    tmp_path: Path,
) -> None:
    db_path = _db(tmp_path)
    kwargs = {
        "severity": "high",
        "category": "security",
        "rule_id": "hardcoded_secret",
        "file_path": "core/example.py",
        "start_line": 12,
        "end_line": 12,
        "description": "Synthetic hardcoded secret finding.",
        "recommendation": "Move secret material to approved configuration.",
        "scan_id": "scan-validation-security-test",
        "context": TelemetryContext(
            project_id="dream-studio",
            milestone_id="validation_security_telemetry_emitters",
            task_id="security-test",
            process_run_id="process-security-test",
            source_refs=("control/analysis/bugs.py",),
            evidence_refs=("security_bridge_evidence.yaml",),
        ),
        "db_path": db_path,
        "mode": MODE_STRICT,
    }

    first = emit_security_finding(**kwargs)
    second = emit_security_finding(**kwargs)

    assert first.emitted is True
    assert second.emitted is False
    assert second.record_id == first.record_id
    conn = _connect(db_path)
    try:
        finding = conn.execute(
            "SELECT severity, file_path, line_number FROM security_events WHERE event_id = ? AND event_kind = 'finding.recorded'",
            (first.record_id,),
        ).fetchone()
        assert dict(finding) == {
            "severity": "high",
            "file_path": "core/example.py",
            "line_number": 12,
        }
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM security_events WHERE event_kind = 'finding.recorded'"
            ).fetchone()[0]
            == 1
        )
        # dashboard_attention_items dropped migration 139 (WO-AI-SPINE, AD-5) — pure
        # duplication; the security_events row above (open, high severity) is
        # already the attention-worthy signal, fully queryable on that spine.
    finally:
        conn.close()


def test_legacy_security_bug_bridge_dual_writes_finding(tmp_path: Path, monkeypatch) -> None:
    db_path = _db(tmp_path)
    monkeypatch.setenv("DREAM_STUDIO_TELEMETRY_DB", str(db_path))

    _emit_security_bug_telemetry(
        {
            "type": "security_flaw",
            "pattern": "sql_injection",
            "category": "security",
            "severity": "critical",
            "file": "core/query.py",
            "line": 44,
            "issue": "Potential SQL injection",
            "fix_recommendation": "Use parameterized queries",
        },
        "bug-sql-injection-test",
    )

    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT severity, vuln_class, file_path, line_number FROM security_events WHERE event_kind = 'finding.recorded'"
        ).fetchone()
        assert row["severity"] == "critical"
        assert row["vuln_class"] == "sql_injection"
        assert row["file_path"] == "core/query.py"
        assert row["line_number"] == 44
    finally:
        conn.close()


def test_store_bugs_persists_all_categories_not_just_security(tmp_path: Path, monkeypatch) -> None:
    # WO-PI-BUGS-REPOINT: _store_bugs no longer writes the removed pi_bugs table;
    # every finding (security AND non-security) is persisted to security_events,
    # so non-security bugs are not dropped.
    db_path = _db(tmp_path)
    monkeypatch.setenv("DREAM_STUDIO_TELEMETRY_DB", str(db_path))

    _store_bugs(
        [
            {
                "type": "security_flaw",
                "pattern": "sql_injection",
                "category": "security",
                "severity": "critical",
                "file": "a.py",
                "line": 1,
                "issue": "SQLi",
            },
            {
                "type": "logic_error",
                "pattern": "null_deref",
                "category": "logic",
                "severity": "high",
                "file": "b.py",
                "line": 2,
                "issue": "Null deref",
            },
        ]
    )

    conn = _connect(db_path)
    try:
        vuln_classes = {
            r["vuln_class"]
            for r in conn.execute(
                "SELECT vuln_class FROM security_events WHERE event_kind = 'finding.recorded'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert vuln_classes == {
        "sql_injection",
        "null_deref",
    }, f"both findings must persist (non-security not dropped); got {vuln_classes}"


def test_validation_and_security_emitters_best_effort_failure_does_not_raise(
    tmp_path: Path,
) -> None:
    empty_db = tmp_path / "empty.db"

    validation = emit_validation_result(
        validation_type="focused_pytest",
        status="passed",
        db_path=empty_db,
    )
    security = emit_security_finding(
        severity="high",
        description="Synthetic finding",
        rule_id="TEST",
        file_path="example.py",
        start_line=1,
        db_path=empty_db,
    )

    assert validation.emitted is False
    assert validation.error
    assert security.emitted is False
    assert security.error
