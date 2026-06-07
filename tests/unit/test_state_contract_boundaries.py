"""Phase 7B operational state contract boundary tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs" / "contracts" / "state-contract.md"

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
            r"\bINSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|VALUES\b)",
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


def _sql_writes_under(root: Path) -> list[tuple[str, str, str]]:
    writes: list[tuple[str, str, str]] = []
    for path in sorted(root.rglob("*.py")):
        source = _read(path)
        for operation, pattern in SQL_WRITE_PATTERNS:
            for match in pattern.finditer(source):
                table = match.group(1)
                writes.append((path.relative_to(REPO_ROOT).as_posix(), operation, table))
    return writes


def test_state_contract_document_defines_required_categories_and_classes():
    contract = _read(CONTRACT_PATH)

    for section in [
        "## Authority Principles",
        "## State Classes",
        "## Ownership Matrix",
        "## Duplicate And Ambiguous State",
        "## Read-Only Projection Rules",
        "## Adapter Boundary Rules",
        "## Telemetry Boundary Rules",
        "## Replay And Rebuild Expectations",
        "## Schema Posture",
    ]:
        assert section in contract

    for state_class in [
        "Canonical",
        "Derived",
        "Advisory",
        "Diagnostic",
        "Transient",
    ]:
        assert state_class in contract

    for category in [
        "workflow state",
        "orchestration state",
        "execution state",
        "decision lineage",
        "governance state",
        "telemetry state",
        "memory/continuity state",
    ]:
        assert f"| {category} |" in contract


def test_state_contract_names_high_risk_duplicate_authority_surfaces():
    contract = _read(CONTRACT_PATH)

    for overlap in [
        "`canonical_events` and `activity_log`",
        "`workflows.json`, `raw_workflow_runs`, and `execution_nodes`",
        "`raw_sessions` and `prd_sessions`",
        "`raw_handoffs` and `prd_handoffs`",
        "`decision_log` and `decision.*` canonical events",
        "`raw_skill_telemetry`, `activity_log`, and `adapter_executions`",
        "`memory_entries`, `memory_fts`, and `control.research.memory` indexes",
        "`research_cache` and `raw_research`",
    ]:
        assert overlap in contract

    assert "the owner listed in the matrix wins" in contract


def test_projection_writers_only_touch_projection_owned_tables():
    allowed_exact = {
        "projection_checkpoints",
        "consumer_state",
        "workflow_executions",
        "workflow_phases",
        "workflow_kpis",
        "phase_kpis",
        "projection_retry_queue",
        "projection_dead_letter",
        "projection_state",
    }
    offenders: list[str] = []

    for rel_path, operation, table in _sql_writes_under(REPO_ROOT / "core" / "projections"):
        if table.startswith("proj_") or table in allowed_exact:
            continue
        offenders.append(f"{rel_path}: {operation} {table}")

    assert offenders == []


def test_projection_api_route_write_exceptions_stay_explicit():
    writes = _sql_writes_under(REPO_ROOT / "projections" / "api" / "routes")

    assert sorted(writes) == [
        ("projections/api/routes/audits.py", "INSERT INTO", "audit_runs"),
    ]


def test_adapters_do_not_open_or_mutate_operational_state():
    adapter_root = REPO_ROOT / "interfaces" / "adapters"
    writes = _sql_writes_under(adapter_root)
    direct_db_tokens = [
        "transaction(",
        "get_connection(",
        "DatabaseContext(",
        "sqlite3.connect",
    ]
    offenders: list[str] = []

    for path in sorted(adapter_root.rglob("*.py")):
        source = _read(path)
        for token in direct_db_tokens:
            if token in source:
                offenders.append(f"{path.relative_to(REPO_ROOT)} contains {token}")

    assert writes == []
    assert offenders == []


def test_telemetry_modules_do_not_mutate_authoritative_state_tables_directly():
    telemetry_paths = list((REPO_ROOT / "core" / "telemetry").rglob("*.py")) + [
        REPO_ROOT / "runtime" / "hooks" / "meta" / "on-skill-telemetry.py",
        REPO_ROOT / "runtime" / "hooks" / "meta" / "on-token-log.py",
        REPO_ROOT / "runtime" / "hooks" / "meta" / "on-tool-activity.py",
    ]
    forbidden_tables = [
        "canonical_events",
        "activity_log",
        "execution_nodes",
        "execution_dependencies",
        "execution_outputs",
        "decision_log",
        "decision_event_link",
        "memory_entries",
        "guardrail_decisions",
    ]
    offenders: list[str] = []

    for path in telemetry_paths:
        source = _read(path)
        for table in forbidden_tables:
            if table in source:
                offenders.append(f"{path.relative_to(REPO_ROOT)} references {table}")

    assert offenders == []


def test_memory_retrieval_remains_rebuildable_projection_of_memory_entries():
    store_source = _read(REPO_ROOT / "core" / "memory" / "store.py")
    retrieval_source = _read(REPO_ROOT / "core" / "memory" / "retrieval.py")
    migration_source = _read(
        REPO_ROOT / "core" / "event_store" / "migrations" / "033_memory_fts.sql"
    )

    assert "memory_entries is the canonical semantic memory authority" in store_source
    assert "The retrieval layer is a PROJECTION of memory_entries" in retrieval_source
    assert "FTS5 indexes are disposable acceleration structures" in retrieval_source
    assert "This is a PROJECTION (rebuildable) index" in migration_source
