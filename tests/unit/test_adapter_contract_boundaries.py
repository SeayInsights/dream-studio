"""Phase 7D adapter contract boundary tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs" / "contracts" / "adapter-contract.md"
ADAPTER_ROOT = REPO_ROOT / "interfaces" / "adapters"

VENDOR_IMPORT_PATTERN = re.compile(
    r"^\s*(?:from|import)\s+"
    r"(openai|anthropic|google\.generativeai|google_genai|litellm|ollama|"
    r"mistralai|cohere|groq|cursor|mcp|claude)\b",
    re.MULTILINE,
)

ADAPTER_IMPORT_PATTERN = re.compile(
    r"^\s*(?:from|import)\s+(interfaces\.adapters|adapters)\b",
    re.MULTILINE,
)

SQL_WRITE_PATTERNS = [
    re.compile(
        r"\bINSERT(?:\s+OR\s+(?:REPLACE|IGNORE|ROLLBACK|ABORT|FAIL))?"
        r"\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|VALUES\b)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bUPDATE\s+([A-Za-z_][A-Za-z0-9_]*)\s+SET\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bDELETE\s+FROM\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:WHERE\b|$)",
        re.IGNORECASE,
    ),
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _python_files(*roots: Path) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        else:
            files.extend(sorted(root.rglob("*.py")))
    return [path for path in files if ".venv" not in path.parts and "__pycache__" not in path.parts]


def _sql_write_tables(source: str) -> list[str]:
    tables: list[str] = []
    for pattern in SQL_WRITE_PATTERNS:
        tables.extend(match.group(1) for match in pattern.finditer(source))
    return tables


def test_adapter_contract_document_defines_status_audit_and_boundaries():
    contract = _read(CONTRACT_PATH)

    for section in [
        "## Authority Principles",
        "## Adapter Responsibilities",
        "## Adapter Prohibitions",
        "## Current Adapter Status",
        "## Boundary Checklist",
        "## Import And Dependency Audit",
        "## Event And State Interactions",
        "## Existing Exceptions And Risks",
        "## Replay, Export, And Health Expectations",
        "## Schema Posture",
    ]:
        assert section in contract

    for required_phrase in [
        "Local canonical runtime state remains authoritative",
        "`source_type` according to the event contract",
        "`interfaces/adapters/models.py`",
        "`core.event_store.studio_db` adapter bootstrap",
        "`control.analysis.engine` normalizer import",
        "`core.execution.github_adapter`",
        "`adapter_executions` is metadata",
        "Phase 7D does not require schema changes",
    ]:
        assert required_phrase in contract


def test_adapter_interfaces_do_not_persist_or_call_external_services():
    forbidden_tokens = [
        "sqlite3",
        "get_connection(",
        "transaction(",
        "DatabaseContext(",
        "EventStore(",
        "emit_event(",
        "urllib.",
        "requests.",
        "httpx.",
        "subprocess.",
    ]
    offenders: list[str] = []

    for path in _python_files(ADAPTER_ROOT):
        source = _read(path)
        for table in _sql_write_tables(source):
            offenders.append(f"{_rel(path)} writes {table}")
        for token in forbidden_tokens:
            if token in source:
                offenders.append(f"{_rel(path)} contains {token}")
        for match in VENDOR_IMPORT_PATTERN.finditer(source):
            offenders.append(f"{_rel(path)} imports vendor package {match.group(1)}")

    assert offenders == []


def test_production_code_has_no_direct_vendor_sdk_imports():
    production_roots = [
        REPO_ROOT / "core",
        REPO_ROOT / "control",
        REPO_ROOT / "runtime",
        REPO_ROOT / "projections",
        REPO_ROOT / "interfaces",
    ]
    offenders: list[str] = []

    for path in _python_files(*production_roots):
        source = _read(path)
        for match in VENDOR_IMPORT_PATTERN.finditer(source):
            offenders.append(f"{_rel(path)} imports {match.group(1)}")

    assert offenders == []


def test_runtime_and_projection_layers_do_not_import_adapter_interfaces_directly():
    offenders: list[str] = []

    for path in _python_files(REPO_ROOT / "runtime", REPO_ROOT / "projections"):
        source = _read(path)
        for match in ADAPTER_IMPORT_PATTERN.finditer(source):
            offenders.append(f"{_rel(path)} imports {match.group(1)}")

    assert offenders == []


def test_core_and_control_adapter_imports_are_limited_and_classified():
    contract = _read(CONTRACT_PATH)
    import_files: set[str] = set()

    for path in _python_files(REPO_ROOT / "core", REPO_ROOT / "control"):
        source = _read(path)
        if ADAPTER_IMPORT_PATTERN.search(source):
            import_files.add(_rel(path))

    assert import_files == {
        "control/analysis/engine.py",
        "core/event_store/studio_db.py",
    }
    assert "`core/event_store/studio_db.py` imports" in contract
    assert "`control/analysis/engine.py` imports" in contract


def test_legacy_top_level_adapters_imports_are_absent():
    top_level_imports: set[str] = set()
    for path in _python_files(REPO_ROOT):
        if "tests" in path.relative_to(REPO_ROOT).parts:
            continue
        source = _read(path)
        if re.search(r"^\s*from\s+adapters\s+import\b", source, re.MULTILINE):
            top_level_imports.add(_rel(path))

    assert top_level_imports == set()


def test_adapter_metadata_table_remains_diagnostic_not_authoritative_writer():
    migration = _read(
        REPO_ROOT / "core" / "event_store" / "migrations" / "030_adapter_metadata.sql"
    )
    contract = _read(CONTRACT_PATH)
    writers: list[str] = []

    for path in _python_files(
        REPO_ROOT / "core",
        REPO_ROOT / "control",
        REPO_ROOT / "runtime",
        REPO_ROOT / "projections",
        REPO_ROOT / "interfaces",
    ):
        if "migrations" in path.parts:
            continue
        source = _read(path)
        if re.search(r"\bINSERT\s+INTO\s+adapter_executions\b", source, re.IGNORECASE):
            writers.append(_rel(path))

    assert "CREATE TABLE IF NOT EXISTS adapter_executions" in migration
    assert "FOREIGN KEY (activity_id) REFERENCES activity_log" in migration
    assert "Diagnostic adapter metadata such as `adapter_executions`" in contract
    assert writers == []


def test_core_skill_logging_bootstrap_keeps_normalizer_available():
    from core.event_store import studio_db

    contract = _read(CONTRACT_PATH)

    assert studio_db._NORMALIZER_AVAILABLE is True
    assert studio_db._event_normalizer.is_registered("claude") is True
    assert "required by legacy skill/activity logging" in contract
