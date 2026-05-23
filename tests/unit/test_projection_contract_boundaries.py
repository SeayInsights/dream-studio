"""Phase 7C projection contract boundary tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs" / "contracts" / "projection-contract.md"

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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _python_files(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if "tests" not in path.relative_to(REPO_ROOT).parts
        and path.name.startswith("test_") is False
    ]


def _sql_writes_under(root: Path) -> list[tuple[str, str, str]]:
    writes: list[tuple[str, str, str]] = []
    for path in _python_files(root):
        source = _read(path)
        for operation, pattern in SQL_WRITE_PATTERNS:
            for match in pattern.finditer(source):
                writes.append((_rel(path), operation, match.group(1)))
    return writes


def test_projection_contract_document_defines_rules_and_matrices():
    contract = _read(CONTRACT_PATH)

    for section in [
        "## Authority Principles",
        "## Projection Classes",
        "## Table Ownership Matrix",
        "## Route Ownership Matrix",
        "## Write Classification Rules",
        "## Dashboard Rules",
        "## Export Rules",
        "## Rebuild Rules",
        "## Violations",
        "## Schema Posture",
    ]:
        assert section in contract

    for projection_class in [
        "Rebuildable projection",
        "Projection metadata",
        "Advisory projection",
        "Governance ingestion exception",
        "Authority violation",
    ]:
        assert projection_class in contract

    for table in [
        "`proj_workflow_runs`",
        "`projection_checkpoints`",
        "`consumer_state`",
        "`workflow_executions`",
        "`workflow_phases`",
        "`workflow_kpis`",
        "`phase_kpis`",
        "`pi_components`",
        "`pi_dependencies`",
        "`alert_rules`",
        "`scheduled_reports`",
        "`audit_runs`",
        "`research_cache`",
    ]:
        assert table in contract


def test_route_ownership_matrix_names_every_api_route_group():
    contract = _read(CONTRACT_PATH)

    for route_group in [
        "`analytics.py`",
        "`metrics.py`",
        "`insights.py`",
        "`intelligence.py`",
        "`hooks.py`",
        "`security.py` GET routes",
        "`security.py` SARIF import route",
        "`audits.py`",
        "`alerts.py`",
        "`schedules.py`",
        "`reports.py`",
        "`exports.py`",
        "`realtime.py`",
        "`prd.py`",
        "`project_intelligence.py`",
        "`discovery_internal.py`",
        "`discovery_external.py`",
        "`discovery_research.py`",
        "`frontend.py`",
        "`ml.py`",
    ]:
        assert route_group in contract


def test_core_projection_writers_only_touch_projection_owned_tables():
    allowed_exact = {
        "projection_checkpoints",
        "consumer_state",
        "workflow_executions",
        "workflow_phases",
        "workflow_kpis",
        "phase_kpis",
        # v2 framework meta-tables — framework.py is the canonical owner
        "projection_state",
        "projection_retry_queue",
        "projection_dead_letter",
    }
    offenders: list[str] = []

    for rel_path, operation, table in _sql_writes_under(REPO_ROOT / "core" / "projections"):
        if table.startswith("proj_") or table in allowed_exact:
            continue
        offenders.append(f"{rel_path}: {operation} {table}")

    assert offenders == []


def test_projection_service_state_writers_stay_limited_and_classified():
    allowed_service_tables = {
        "alert_rules",
        "alert_history",
        "sla_definitions",
        "scheduled_reports",
        # execution_events_projection.py projects canonical execution events into this L3 table
        "execution_events",
    }
    writes = _sql_writes_under(REPO_ROOT / "projections" / "core")
    offenders = [
        f"{rel_path}: {operation} {table}"
        for rel_path, operation, table in writes
        if table not in allowed_service_tables
    ]

    assert offenders == []


def test_api_route_direct_sql_writes_stay_explicitly_classified():
    writes = sorted(_sql_writes_under(REPO_ROOT / "projections" / "api" / "routes"))

    assert writes == [
        ("projections/api/routes/audits.py", "INSERT INTO", "audit_runs"),
        ("projections/api/routes/discovery_research.py", "DELETE FROM", "research_cache"),
    ]


def test_api_routes_do_not_directly_write_canonical_runtime_tables():
    forbidden_tables = {
        "canonical_events",
        "activity_log",
        "execution_nodes",
        "execution_dependencies",
        "execution_outputs",
        "decision_log",
        "decision_event_link",
        "memory_entries",
        "raw_sessions",
        "raw_workflow_runs",
        "hook_executions",
        "adapter_executions",
        "risk_register",
        "guardrail_decisions",
        "sec_sarif_findings",
    }
    offenders = [
        f"{rel_path}: {operation} {table}"
        for rel_path, operation, table in _sql_writes_under(
            REPO_ROOT / "projections" / "api" / "routes"
        )
        if table in forbidden_tables
    ]

    assert offenders == []


@pytest.mark.xfail(
    reason="activity_log dropped in migration 063; sarif_parser and engine now write via canonical event spool",
    strict=True,
)
def test_projection_namespace_activity_log_writers_remain_named_exceptions():
    activity_log_writers = sorted(
        (rel_path, table)
        for rel_path, operation, table in _sql_writes_under(REPO_ROOT / "projections")
        if table == "activity_log"
    )
    contract = _read(CONTRACT_PATH)

    assert sorted(set(activity_log_writers)) == [
        ("projections/parsers/sarif_parser.py", "activity_log"),
        ("projections/scoring/engine.py", "activity_log"),
    ]
    assert "`activity_log` from `sarif_parser`" in contract
    assert "`activity_log` from `RiskScoringEngine`" in contract


def test_dashboard_frontend_does_not_open_database_or_write_state():
    frontend_root = REPO_ROOT / "projections" / "frontend"
    forbidden_tokens = [
        "sqlite3",
        "get_connection",
        "transaction(",
        "EventStore(",
        "emit_event(",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
    ]
    offenders: list[str] = []

    for path in sorted(frontend_root.rglob("*")):
        if path.suffix.lower() not in {".html", ".js", ".css", ".py"}:
            continue
        source = _read(path)
        for token in forbidden_tokens:
            if token in source:
                offenders.append(f"{_rel(path)} contains {token}")

    assert offenders == []


def test_route_service_write_exceptions_are_visible_in_contract():
    contract = _read(CONTRACT_PATH)
    alerts_source = _read(REPO_ROOT / "projections" / "api" / "routes" / "alerts.py")
    schedules_source = _read(REPO_ROOT / "projections" / "api" / "routes" / "schedules.py")

    assert "RuleManager" in alerts_source
    assert "SLATracker" in alerts_source
    assert "ScheduleStorage" in schedules_source
    assert "`alert_rules`" in contract
    assert "`alert_history`" in contract
    assert "`sla_definitions`" in contract
    assert "`scheduled_reports`" in contract
