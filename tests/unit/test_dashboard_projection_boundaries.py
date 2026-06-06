"""Phase 9B dashboard/API/projection authority guardrails."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECTION_CONTRACT = REPO_ROOT / "docs" / "contracts" / "projection-contract.md"

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

FETCH_WITH_OPTIONS = re.compile(
    r"fetch\(\s*(?P<endpoint>`[^`]+`|'[^']+'|\"[^\"]+\")\s*,\s*\{(?P<options>.*?)\}\s*\)",
    re.DOTALL,
)
HTTP_METHOD = re.compile(r"method\s*:\s*['\"](?P<method>POST|PUT|PATCH|DELETE)['\"]", re.IGNORECASE)

ALLOWED_DASHBOARD_WRITES = [
    (
        re.compile(r"^/api/v1/alerts/rules(?:/.*)?$"),
        {"POST", "PUT", "DELETE"},
        "alert service state",
    ),
    (re.compile(r"^/api/v1/security/sarif/import$"), {"POST"}, "SARIF governance ingestion"),
]

CANONICAL_STATE_TABLES = {
    "canonical_events",
    "execution_nodes",
    "execution_dependencies",
    "execution_outputs",
    "raw_workflow_runs",
    "raw_workflow_nodes",
    "decision_log",
    "decision_event_link",
    "memory_entries",
    "hook_executions",
    "adapter_executions",
    "guardrail_decisions",
}

PROJECTION_SERVICE_TABLES = {
    "alert_rules",
    "alert_history",
    "sla_definitions",
}


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


def _sql_writes_in_file(path: Path) -> list[tuple[str, str, str]]:
    source = _read(path)
    writes: list[tuple[str, str, str]] = []
    for operation, pattern in SQL_WRITE_PATTERNS:
        for match in pattern.finditer(source):
            writes.append((_rel(path), operation, match.group(1)))
    return writes


def _sql_writes_under(root: Path) -> list[tuple[str, str, str]]:
    writes: list[tuple[str, str, str]] = []
    for path in _python_files(root):
        writes.extend(_sql_writes_in_file(path))
    return sorted(writes)


def _is_allowed_dashboard_write(endpoint: str, method: str) -> bool:
    for pattern, methods, _reason in ALLOWED_DASHBOARD_WRITES:
        if pattern.match(endpoint) and method in methods:
            return True
    return False


def _dashboard_write_calls() -> list[tuple[str, str, str]]:
    calls: list[tuple[str, str, str]] = []
    for path in [REPO_ROOT / "projections" / "frontend" / "dashboard.html"]:
        source = _read(path)
        for match in FETCH_WITH_OPTIONS.finditer(source):
            method_match = HTTP_METHOD.search(match.group("options"))
            if not method_match:
                continue
            endpoint = match.group("endpoint").strip("\"'`")
            calls.append((_rel(path), method_match.group("method").upper(), endpoint))
    return sorted(calls)


def test_dashboard_write_like_calls_stay_on_named_api_exceptions():
    write_calls = _dashboard_write_calls()

    assert write_calls == [
        ("projections/frontend/dashboard.html", "POST", "/api/v1/alerts/rules"),
        ("projections/frontend/dashboard.html", "POST", "/api/v1/security/sarif/import"),
        ("projections/frontend/dashboard.html", "PUT", "/api/v1/alerts/rules/${ruleId}"),
    ]

    offenders = [
        f"{rel_path}: {method} {endpoint}"
        for rel_path, method, endpoint in write_calls
        if not _is_allowed_dashboard_write(endpoint, method)
    ]
    assert offenders == []


def test_projection_api_direct_writes_stay_named_and_noncanonical():
    allowed_route_writes = {
        ("projections/api/routes/audits.py", "INSERT INTO", "audit_runs"),
        ("projections/api/routes/discovery_research.py", "DELETE FROM", "research_cache"),
        # Phase 19.2: dismiss endpoint sets findings.dismissed_at + dismissed_reason.
        # findings is telemetry (not canonical state) so this write is intentional.
        ("projections/api/routes/security.py", "UPDATE", "findings"),
    }
    route_writes = set(_sql_writes_under(REPO_ROOT / "projections" / "api" / "routes"))

    assert route_writes == allowed_route_writes
    canonical_offenders = [
        f"{rel_path}: {operation} {table}"
        for rel_path, operation, table in sorted(route_writes)
        if table in CANONICAL_STATE_TABLES
    ]
    assert canonical_offenders == []


def test_projection_api_write_helpers_stay_explicitly_scoped():
    helper_tokens = ("transaction(", "_db_transaction(")
    helper_users: list[tuple[str, str]] = []

    for path in _python_files(REPO_ROOT / "projections" / "api" / "routes"):
        source = _read(path)
        for token in helper_tokens:
            if token in source:
                helper_users.append((_rel(path), token))

    assert sorted(helper_users) == [
        ("projections/api/routes/audits.py", "transaction("),
    ]


def test_projection_api_event_emission_stays_absent_or_classified():
    direct_forbidden = [
        "emit_event(",
        "EventStore(",
        "write_event(",
        "INSERT INTO canonical_events",
        "UPDATE canonical_events",
        "DELETE FROM canonical_events",
    ]
    direct_offenders: list[str] = []

    for path in _python_files(REPO_ROOT / "projections" / "api"):
        source = _read(path)
        for token in direct_forbidden:
            if token in source:
                direct_offenders.append(f"{_rel(path)} contains {token}")

    assert direct_offenders == []

    indirect_research_users = [
        _rel(path)
        for path in _python_files(REPO_ROOT / "projections" / "api" / "routes")
        if "from control.research import web as web_research" in _read(path)
    ]
    assert indirect_research_users == ["projections/api/routes/discovery_research.py"]

    discovery_source = _read(REPO_ROOT / "projections" / "api" / "routes" / "discovery_research.py")
    assert "emit_events=False" in discovery_source

    research_source = _read(REPO_ROOT / "control" / "research" / "web.py")
    assert "emit_events: bool = True" in research_source
    assert "if emit_events:" in research_source
    assert sorted(set(re.findall(r"EventType\.([A-Z_]+)", research_source))) == [
        "RESEARCH_CACHE_CLEARED",
        "RESEARCH_CACHE_STORED",
    ]
    contract = _read(PROJECTION_CONTRACT)
    assert "`research_cache`" in contract
    assert "advisory cache" in contract


def test_projection_service_state_writers_remain_named_tables_only():
    service_writes = set()
    for root in [
        REPO_ROOT / "projections" / "core" / "alerts",
        REPO_ROOT / "projections" / "core" / "sla",
    ]:
        service_writes.update(_sql_writes_under(root))

    written_tables = {table for _rel_path, _operation, table in service_writes}
    assert written_tables == PROJECTION_SERVICE_TABLES

    canonical_offenders = [
        f"{rel_path}: {operation} {table}"
        for rel_path, operation, table in sorted(service_writes)
        if table in CANONICAL_STATE_TABLES
    ]
    assert canonical_offenders == []

    contract = _read(PROJECTION_CONTRACT)
    for table in sorted(PROJECTION_SERVICE_TABLES):
        assert f"`{table}`" in contract


def test_security_sarif_parser_is_active():
    source = _read(REPO_ROOT / "projections" / "api" / "routes" / "security.py")
    assert "from projections.parsers.sarif_parser import parse_sarif_file" in source
    assert "parse_sarif_file(tmp_path)" in source
    assert "SARIF parser not yet implemented" not in source


def test_package_local_api_integration_tests_remain_classified_until_isolated():
    path = REPO_ROOT / "projections" / "api" / "test_api_integration.py"
    source = _read(path)
    rel_parts = path.relative_to(REPO_ROOT).parts
    is_package_local = rel_parts[:2] == ("projections", "api")
    is_explicitly_isolated = (
        "tmp_path" in source
        and "monkeypatch" in source
        and ("DREAM_STUDIO_HOME" in source or "USERPROFILE" in source or "HOME" in source)
    )
    is_explicitly_opt_in = (
        "DREAM_STUDIO_RUN_LEGACY_API_INTEGRATION" in source and "pytest.mark.skipif" in source
    )

    assert is_package_local or is_explicitly_isolated
    if not is_explicitly_isolated:
        assert is_explicitly_opt_in
        assert "TestClient(app)" in source
