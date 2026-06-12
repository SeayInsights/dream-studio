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
        "`prd.py`",
        "`project_intelligence.py`",
        "`discovery_internal.py`",
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
    # duckdb_projections.py writes to DuckDB (not SQLite studio.db) via a DuckDB connection;
    # its SQL is excluded from the SQLite boundary scan.
    duckdb_rel = "core/projections/duckdb_projections.py"
    offenders: list[str] = []

    for rel_path, operation, table in _sql_writes_under(REPO_ROOT / "core" / "projections"):
        if rel_path == duckdb_rel:
            continue
        if table.startswith("proj_") or table in allowed_exact:
            continue
        offenders.append(f"{rel_path}: {operation} {table}")

    assert offenders == []

    # Confirm the DuckDB projection file is the sole DuckDB-namespaced writer in core/projections.
    duckdb_writers = [
        rel_path
        for rel_path, _op, table in _sql_writes_under(REPO_ROOT / "core" / "projections")
        if table == "duckdb_execution_events"
    ]
    assert duckdb_writers == [
        duckdb_rel
    ], "Only duckdb_projections.py should write to duckdb_execution_events"


def test_projection_service_state_writers_stay_limited_and_classified():
    allowed_service_tables = {
        "alert_rules",
        "alert_history",
        "sla_definitions",
        "scheduled_reports",
        # execution_events_projection.py projects canonical execution events into this L3 table
        "execution_events",
        # analyzer signal tables — L3 derived signals, not canonical authority
        "ds_friction_signals",
        "ds_user_extensions",
        "ds_workflow_pattern_signals",
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
        ("projections/api/routes/extensions_api.py", "UPDATE", "ds_user_extensions"),
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

    assert "RuleManager" in alerts_source
    assert "SLATracker" in alerts_source
    assert "`alert_rules`" in contract
    assert "`alert_history`" in contract
    assert "`sla_definitions`" in contract
