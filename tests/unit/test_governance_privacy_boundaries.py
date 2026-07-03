"""Phase 11B governance/security/privacy authority guardrails."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE_CONTRACT = REPO_ROOT / "docs" / "contracts" / "governance-contract.md"

SQL_WRITE_PATTERNS = [
    (
        "CREATE TABLE",
        re.compile(
            r"\bCREATE\s+(?:VIRTUAL\s+)?TABLE(?:\s+IF\s+NOT\s+EXISTS)?"
            r"\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            re.IGNORECASE,
        ),
    ),
    (
        "INSERT INTO",
        re.compile(
            r"\bINSERT(?:\s+OR\s+(?:REPLACE|IGNORE|ROLLBACK|ABORT|FAIL))?"
            r"\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|VALUES\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "UPDATE",
        re.compile(
            r"\bUPDATE\s+([A-Za-z_][A-Za-z0-9_]*)\s+SET\b",
            re.IGNORECASE,
        ),
    ),
    (
        "DELETE FROM",
        re.compile(
            r"\bDELETE\s+FROM\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:WHERE\b|$)",
            re.IGNORECASE,
        ),
    ),
]

RAW_PRIVATE_TABLES = {
    "memory_entries",
    "raw_sessions",
    "raw_token_usage",
    "validation_failures",
    "canonical_events",
    "raw_handoffs",
}

CANONICAL_AUTHORITY_TABLES = {
    "canonical_events",
    "business_canonical_events",
    "execution_nodes",
    "execution_dependencies",
    "execution_outputs",
    "raw_workflow_runs",
    "raw_workflow_nodes",
    # decision_log / decision_event_link dropped migration 136 (WO-DBA-EVAL-DECISION
    # T4): decisions are decision.recorded events in business_canonical_events.
    "memory_entries",
    "raw_sessions",
    "raw_token_usage",
}

SCANNER_EVIDENCE_TABLES = {
    "activity_log",
    # sec_sarif_findings / sec_cve_matches / sec_manual_reviews retired in migration 112 (WO-Y).
    # Scanner evidence now lands on the security_events spine + findings_current_status.
    "security_events",
    "findings_current_status",
}

AUTHORITY_RESIDUE_TOKENS = {
    "power bi",
    "powerbi",
    "hipaa",
    "pci",
    "soc 2",
    "multi-tenant",
    "single-tenant",
    "tenant_key",
    "github_org",
    "client_profile",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _python_files(*roots: Path) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            files.append(root)
        else:
            files.extend(sorted(root.rglob("*.py")))

    return [path for path in files if "__pycache__" not in path.parts and ".venv" not in path.parts]


def _sql_writes_in_file(path: Path) -> list[tuple[str, str, str]]:
    source = _read(path)
    writes: list[tuple[str, str, str]] = []
    for operation, pattern in SQL_WRITE_PATTERNS:
        for match in pattern.finditer(source):
            writes.append((_rel(path), operation, match.group(1)))
    return writes


def _sql_writes_under(*roots: Path) -> list[tuple[str, str, str]]:
    writes: list[tuple[str, str, str]] = []
    for path in _python_files(*roots):
        writes.extend(_sql_writes_in_file(path))
    return sorted(set(writes))


def _contains_word(source: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", source, re.IGNORECASE) is not None


def test_governance_contract_defines_signal_and_export_boundaries():
    contract = _read(GOVERNANCE_CONTRACT)

    for section in [
        "## Authority Principles",
        "## Signal Ownership",
        "## Privacy And Export Classes",
        "## Export And Backup Rules",
        "## Scanner And Guardrail Rules",
        "## Company And Org Boundaries",
        "## Active Hook Boundary",
        "## Schema Posture",
    ]:
        assert section in contract

    for table in [
        "`audit_runs`",
        "`guardrail_decisions`",
        "`sec_sarif_findings`",
        "`validation_failures`",
        "`memory_entries`",
        "`raw_sessions`",
        "`raw_token_usage`",
        "`canonical_events`",
    ]:
        assert table in contract

    contract_lower = contract.lower()
    assert "scanner output is evidence" in contract_lower
    assert "full db backups are not redacted exports" in contract_lower
    assert "validate_client_profile.py" in contract
    assert "init_security_state.py" in contract
    assert "no active writer in Phase 11C" in contract
    assert "unsupported legacy custom-query fields" in contract


def test_export_privacy_gate_blocks_raw_private_sources():
    from projections.api.models.reports import (
        ExportPrivacyError,
        classify_export_privacy,
        validate_export_payload,
    )

    privacy = classify_export_privacy(sources=["metrics", "insights"])
    assert privacy["classification"] == "derived_projection_snapshot"
    assert privacy["redaction_required"] is False

    with pytest.raises(ExportPrivacyError, match="include_raw_data"):
        classify_export_privacy(include_raw_data=True)

    with pytest.raises(ExportPrivacyError, match="memory_entries"):
        classify_export_privacy(sources=["memory_entries"])

    redacted = classify_export_privacy(
        sources=["canonical_events.payload"],
        redaction_classification="redacted",
    )
    assert redacted["classification"] == "redacted"
    assert redacted["redaction_required"] is True

    with pytest.raises(ExportPrivacyError, match="raw/private local state"):
        validate_export_payload({"sections": [{"metrics": {"raw_sessions": []}}]})


def test_scanner_outputs_write_only_security_evidence_surfaces():
    writes = _sql_writes_under(
        REPO_ROOT / "projections" / "parsers" / "sarif_parser.py",
        REPO_ROOT / "projections" / "scoring" / "engine.py",
        REPO_ROOT / "guardrails" / "scanners",
        REPO_ROOT / "runtime" / "hooks" / "quality" / "on-security-scan.py",
    )

    assert writes == []

    offenders = [
        f"{rel_path}: {operation} {table}"
        for rel_path, operation, table in writes
        if table not in SCANNER_EVIDENCE_TABLES
    ]
    assert offenders == []


def test_scanner_and_scoring_paths_do_not_write_canonical_runtime_authority():
    writes = _sql_writes_under(
        REPO_ROOT / "projections" / "parsers",
        REPO_ROOT / "projections" / "scoring",
        REPO_ROOT / "guardrails" / "scanners",
    )
    canonical_offenders = [
        f"{rel_path}: {operation} {table}"
        for rel_path, operation, table in writes
        if table in CANONICAL_AUTHORITY_TABLES
    ]

    assert canonical_offenders == []


def test_guardrail_evaluator_writes_only_decision_governance_surfaces():
    evaluator = REPO_ROOT / "guardrails" / "evaluator.py"
    source = _read(evaluator)
    writes = _sql_writes_in_file(evaluator)

    # hook_eval_runs write dropped migration 136 (WO-DBA-EVAL-DECISION T4):
    # _write_hook_eval_run now only emits an eval.run.completed canonical event.
    assert writes == [
        ("guardrails/evaluator.py", "INSERT INTO", "guardrail_decisions"),
        ("guardrails/evaluator.py", "INSERT INTO", "guardrail_decisions"),
    ]
    assert "emit_decision(" in source
    # Slice 3: guardrail emitter migrated to spool pipeline
    assert "write_envelopes(" in source
    assert "GUARDRAIL_DECISION" in source

    canonical_offenders = [
        f"{rel_path}: {operation} {table}"
        for rel_path, operation, table in writes
        if table in CANONICAL_AUTHORITY_TABLES
    ]
    assert canonical_offenders == []


def test_guardrail_trigger_fields_are_aligned_to_activity_log_schema():
    evaluator_source = _read(REPO_ROOT / "guardrails" / "evaluator.py")
    contract = _read(GOVERNANCE_CONTRACT)

    for token in [
        "event_type = ?",
        "json_extract(payload, '$.finding_type') = ?",
        "severity = ?",
        "stream_id LIKE",
        "event_id = ?",
    ]:
        assert token in evaluator_source

    for stale_token in [
        "activity_type = ?",
        "json_extract(event_data,",
        "tool_name = ?",
        "activity_id = ?",
    ]:
        assert stale_token not in evaluator_source

    contract_lower = contract.lower()
    assert "supported fields" in contract_lower
    assert "fail closed" in contract_lower


def _activity_log_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE activity_log (
            activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_type TEXT NOT NULL,
            stream_id TEXT,
            stream_type TEXT,
            event_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            event_data TEXT,
            prd_id TEXT,
            task_id TEXT,
            session_id TEXT,
            workflow_run_key TEXT,
            skill_id TEXT,
            status TEXT,
            severity TEXT,
            duration_ms INTEGER,
            is_anomaly BOOLEAN DEFAULT 0,
            anomaly_score REAL DEFAULT 0.0
        )
        """)
    return conn


def _canonical_events_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE canonical_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            trace JSON NOT NULL DEFAULT '{}',
            severity TEXT NOT NULL DEFAULT 'info',
            payload JSON NOT NULL DEFAULT '{}',
            actor JSON,
            confidence_score REAL,
            source_type TEXT,
            raw_prompt_retained INTEGER NOT NULL DEFAULT 0,
            raw_tool_output_retained INTEGER NOT NULL DEFAULT 0,
            schema_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            invocation_mode TEXT
        )
        """)
    return conn


def _guardrail_rule(trigger):
    from guardrails.models import GuardrailAction, GuardrailRule, Severity

    return GuardrailRule(
        rule_id="GR-TEST",
        name="Test Rule",
        trigger=trigger,
        action=GuardrailAction.BLOCK,
        message="blocked",
        severity=Severity.HIGH,
    )


def test_guardrail_trigger_matching_uses_supported_activity_log_fields():
    from guardrails.evaluator import evaluate_rule_trigger
    from guardrails.models import Severity, TriggerCondition

    conn = _canonical_events_conn()
    conn.execute(
        """
        INSERT INTO canonical_events
        (event_id, event_type, timestamp, severity, payload)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "test-event-1",
            "security_finding",
            "2026-05-27T00:00:00+00:00",
            "critical",
            json.dumps(
                {
                    "finding_type": "hardcoded credential",
                    "file_path": "src/app.py",
                }
            ),
        ),
    )
    event_id = "test-event-1"

    matching_trigger = TriggerCondition(
        event_type="security_finding",
        finding_type="hardcoded credential",
        severity=Severity.CRITICAL,
        # tool_name omitted: stream_id/stream_type columns don't exist in canonical_events
        file_pattern=r"src/app\.py",
    )
    assert evaluate_rule_trigger(_guardrail_rule(matching_trigger), event_id, conn)

    missing_trigger = TriggerCondition(event_type="hook_execution", severity=Severity.CRITICAL)
    assert not evaluate_rule_trigger(_guardrail_rule(missing_trigger), event_id, conn)


def test_guardrail_custom_query_rejects_legacy_activity_log_fields():
    from guardrails.evaluator import evaluate_rule_trigger
    from guardrails.models import EvaluationError, TriggerCondition

    conn = _canonical_events_conn()
    conn.execute("""
        INSERT INTO canonical_events (event_id, event_type, timestamp, severity, payload)
        VALUES ('test-2', 'security_finding', '2026-05-27T00:00:00+00:00', 'critical', '{"finding_type":"secret"}')
        """)

    valid_query = TriggerCondition(
        custom_query="SELECT 1 FROM canonical_events WHERE event_type = 'security_finding'"
    )
    assert evaluate_rule_trigger(_guardrail_rule(valid_query), None, conn)

    # activity_log was removed in migration 063; custom_query must use canonical_events.
    legacy_query = TriggerCondition(
        custom_query="SELECT 1 FROM activity_log WHERE activity_type = 'security_finding'"
    )
    with pytest.raises(EvaluationError, match="removed table"):
        evaluate_rule_trigger(_guardrail_rule(legacy_query), None, conn)


def test_security_and_audit_routes_keep_named_write_exceptions_only():
    writes = _sql_writes_under(
        REPO_ROOT / "projections" / "api" / "routes" / "security.py",
        REPO_ROOT / "projections" / "api" / "routes" / "audits.py",
    )

    assert writes == [
        ("projections/api/routes/audits.py", "INSERT INTO", "audit_runs"),
    ]

    canonical_offenders = [
        f"{rel_path}: {operation} {table}"
        for rel_path, operation, table in writes
        if table in CANONICAL_AUTHORITY_TABLES
    ]
    assert canonical_offenders == []


def test_backup_and_cloud_backup_remain_operator_controlled_and_outside_validation():
    dev_script = _read(REPO_ROOT / "scripts" / "dev.ps1")
    backup_cli = _read(REPO_ROOT / "interfaces" / "cli" / "studio_backup.py")
    state_module = _read(REPO_ROOT / "core" / "config" / "state.py")
    contract = _read(GOVERNANCE_CONTRACT)

    assert "studio_backup.py" not in dev_script
    assert "--restore" not in dev_script
    assert "--cloud" not in dev_script

    assert "--restore" in backup_cli
    assert "--export" in backup_cli
    assert "--cloud" in backup_cli
    assert "shutil.copy2" in backup_cli
    assert "Full DB backups are not redacted exports" in backup_cli
    assert "cloud backup is transport only" in backup_cli.lower()

    assert 'if not config.get("auto_push") or not config.get("remote")' in state_module
    assert "subprocess.Popen" in state_module

    contract_lower = contract.lower()
    assert "operator-controlled recovery artifacts" in contract_lower
    assert "optional cloud backup behavior" in contract_lower
    assert "does not create cloud, org, or global authority" in contract_lower


def test_client_org_tooling_is_classified_as_local_only():
    for path in [
        REPO_ROOT / "interfaces" / "cli" / "init_security_state.py",
        REPO_ROOT / "interfaces" / "cli" / "validate_client_profile.py",
    ]:
        source = _read(path).lower()
        assert "local-only optional security/client tooling" in source
        assert "core runtime authority" in source
        assert "org aggregation" in source


def test_active_runtime_hooks_do_not_depend_on_retired_hooks_lib():
    runtime_hooks = REPO_ROOT / "runtime" / "hooks"
    assert runtime_hooks.is_dir()
    assert not (REPO_ROOT / "hooks" / "lib").exists()

    offenders: list[str] = []
    for path in _python_files(runtime_hooks):
        source = _read(path)
        for token in ["hooks/lib", "HOOKS_LIB"]:
            if token in source:
                offenders.append(f"{_rel(path)} contains retired path token {token}")
        if re.search(r"parents\[\d+\]\s*/\s*[\"']hooks[\"']\s*/\s*[\"']lib[\"']", source):
            offenders.append(f"{_rel(path)} builds retired hooks/lib path")

    assert offenders == []


def test_company_client_org_assumptions_stay_out_of_authority_paths():
    authority_roots = [
        REPO_ROOT / "core" / "event_store",
        REPO_ROOT / "core" / "events",
        REPO_ROOT / "core" / "execution",
        REPO_ROOT / "core" / "memory",
        REPO_ROOT / "core" / "decisions",
        REPO_ROOT / "core" / "config",
        REPO_ROOT / "runtime" / "hooks",
    ]
    offenders: list[str] = []

    for path in _python_files(*authority_roots):
        if "migrations" in path.parts:
            continue
        source = _read(path).lower()
        for token in sorted(AUTHORITY_RESIDUE_TOKENS):
            if token in source:
                offenders.append(f"{_rel(path)} contains company/org residue token {token!r}")

    assert offenders == []
