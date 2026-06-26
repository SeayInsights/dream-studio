"""Integration contract boundary guardrails.

Replaces tests/unit/test_adapter_contract_boundaries.py.
Verifies that integrations/ is non-authoritative: no vendor SDK imports,
no direct DB writes, no subprocess/network calls.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[3]
INTEGRATIONS_ROOT = REPO_ROOT / "integrations"

VENDOR_IMPORT_PATTERN = re.compile(
    r"^\s*(?:from|import)\s+"
    r"(openai|anthropic|google\.generativeai|google_genai|litellm|ollama|"
    r"mistralai|cohere|groq|cursor|mcp|claude)\b",
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

INTEGRATION_FORBIDDEN_TOKENS = [
    "sqlite3.connect(",
    "sqlite3.cursor(",
    "get_connection(",
    "transaction(",
    "DatabaseContext(",
    "EventStore(",
    "urllib.",
    "requests.",
    "httpx.",
    "subprocess.",
]


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
    return [path for path in files if ".venv" not in path.parts and "__pycache__" not in path.parts]


def _sql_write_tables(source: str) -> list[str]:
    tables: list[str] = []
    for pattern in SQL_WRITE_PATTERNS:
        tables.extend(match.group(1) for match in pattern.finditer(source))
    return tables


def test_integrations_layer_has_no_vendor_sdk_imports():
    offenders: list[str] = []
    for path in _python_files(INTEGRATIONS_ROOT):
        source = _read(path)
        for match in VENDOR_IMPORT_PATTERN.finditer(source):
            offenders.append(f"{_rel(path)} imports {match.group(1)}")
    assert offenders == []


def test_integrations_layer_does_not_write_authority_db_directly():
    offenders: list[str] = []
    for path in _python_files(INTEGRATIONS_ROOT):
        source = _read(path)
        for table in _sql_write_tables(source):
            offenders.append(f"{_rel(path)} writes SQL table {table!r}")
        for token in INTEGRATION_FORBIDDEN_TOKENS:
            if token in source:
                offenders.append(f"{_rel(path)} contains forbidden token {token!r}")
    assert offenders == []


def test_integrations_layer_does_not_import_adapter_interfaces():
    offenders: list[str] = []
    for path in _python_files(INTEGRATIONS_ROOT):
        source = _read(path)
        if re.search(r"^\s*from\s+adapters\s+import\b", source, re.MULTILINE):
            offenders.append(_rel(path))
        if re.search(r"^\s*(?:from|import)\s+interfaces\.adapters\b", source, re.MULTILINE):
            offenders.append(_rel(path))
    assert offenders == []


def test_legacy_top_level_adapters_imports_absent_from_new_layers():
    """integrations/, emitters/, canonical/, spool/ must not use legacy `from adapters import`."""
    new_layer_roots = [
        REPO_ROOT / "integrations",
        REPO_ROOT / "emitters",
        REPO_ROOT / "canonical",
        REPO_ROOT / "spool",
    ]
    offenders: set[str] = set()
    for path in _python_files(*new_layer_roots):
        source = _read(path)
        if re.search(r"^\s*from\s+adapters\s+import\b", source, re.MULTILINE):
            offenders.add(_rel(path))
    assert offenders == set()


def test_core_skill_logging_bootstrap_keeps_normalizer_available():
    from core.event_store import studio_db

    assert studio_db._NORMALIZER_AVAILABLE is True
    assert studio_db._event_normalizer.is_registered("claude") is True
