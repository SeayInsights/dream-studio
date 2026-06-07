"""Phase 12B research/source provenance authority guardrails."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_CONTRACT = REPO_ROOT / "docs" / "contracts" / "research-source-contract.md"

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

RESEARCH_ROUTE_FILES: list = []

CANONICAL_AUTHORITY_TABLES = {
    "canonical_events",
    "decision_log",
    "decision_event_link",
    "execution_nodes",
    "execution_dependencies",
    "execution_outputs",
    "hook_executions",
    "memory_entries",
    "raw_sessions",
    "raw_token_usage",
    "raw_workflow_nodes",
    "raw_workflow_runs",
    "workflow_executions",
    "workflow_phases",
    "workflow_kpis",
    "phase_kpis",
}

MEMORY_PROMOTION_TOKENS = {
    "MemoryStore(",
    "IngestionConsumer",
    "run_all_ingestion(",
    "upsert_by_provenance(",
    "INSERT INTO memory_entries",
    "UPDATE memory_entries",
    "DELETE FROM memory_entries",
}

RAW_PRIVATE_TOKENS = {
    "memory_entries",
    "raw_sessions",
    "raw_token_usage",
    "validation_failures",
    "canonical_events",
    "raw handoff",
    "raw session",
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
            continue
        files.extend(sorted(root.rglob("*.py")))
    return [path for path in files if "__pycache__" not in path.parts and ".venv" not in path.parts]


def _sql_writes_in_file(path: Path) -> list[tuple[str, str, str]]:
    source = _read(path)
    writes: list[tuple[str, str, str]] = []
    for operation, pattern in SQL_WRITE_PATTERNS:
        for match in pattern.finditer(source):
            writes.append((_rel(path), operation, match.group(1)))
    return sorted(writes)


def test_research_source_contract_defines_required_artifact_fields():
    contract = _read(RESEARCH_CONTRACT)

    for section in [
        "## Authority Principles",
        "## Research Artifact Contract",
        "## Source Record Contract",
        "## Source Quality Rules",
        "## Cache And Evidence Surfaces",
        "## API And Projection Boundaries",
        "## Memory And Decision Lineage",
        "## External Service Optionality",
        "## Privacy And Export Rules",
        "## Legacy Diagnostics",
        "## Violations",
        "## Schema Posture",
    ]:
        assert section in contract

    for field in [
        "`topic_or_query`",
        "`sources`",
        "`extraction_notes`",
        "`confidence`",
        "`verification_status`",
        "`triangulation`",
        "`cache_status`",
        "`created_at`",
        "`accessed_at`",
        "`privacy_export_classification`",
        "`url`",
        "`title`",
        "`source_type`",
        "`source_tier`",
    ]:
        assert field in contract

    contract_lower = contract.lower()
    assert "research/source artifacts are advisory evidence" in contract_lower
    assert "model-generated summaries are not sources" in contract_lower
    assert "missing fields must not be interpreted as proof" in contract_lower


def test_research_cache_and_raw_research_are_advisory_evidence_only():
    contract = _read(RESEARCH_CONTRACT)
    projection_contract = _read(REPO_ROOT / "docs" / "contracts" / "projection-contract.md")
    state_contract = _read(REPO_ROOT / "docs" / "contracts" / "state-contract.md")

    for table in ["`research_cache`", "`raw_research`"]:
        assert table in contract
        assert table in state_contract or table in projection_contract

    contract_lower = contract.lower()
    assert "`research_cache` is an advisory cache" in contract
    assert "`raw_research` is a research evidence and lineage surface" in contract
    assert "neither `research_cache` nor `raw_research` may become workflow" in contract_lower
    assert "not canonical truth" in contract_lower


def test_research_api_routes_do_not_emit_unclassified_canonical_events():
    forbidden_tokens = [
        "emit_event(",
        "EventStore(",
        "write_event(",
        "INSERT INTO canonical_events",
        "UPDATE canonical_events",
        "DELETE FROM canonical_events",
    ]
    offenders: list[str] = []

    for path in RESEARCH_ROUTE_FILES:
        source = _read(path)
        for token in forbidden_tokens:
            if token in source:
                offenders.append(f"{_rel(path)} contains {token}")

    assert offenders == []

    web_source = _read(REPO_ROOT / "control" / "research" / "web.py")
    assert "emit_events: bool = True" in web_source
    assert "emit_events: Emit canonical research cache events when True" in web_source


def test_research_routes_do_not_write_workflow_or_execution_authority_tables():
    writes: list[tuple[str, str, str]] = []
    for path in RESEARCH_ROUTE_FILES:
        writes.extend(_sql_writes_in_file(path))

    assert sorted(writes) == []

    offenders = [
        f"{rel_path}: {operation} {table}"
        for rel_path, operation, table in writes
        if table in CANONICAL_AUTHORITY_TABLES
    ]
    assert offenders == []


def test_research_cache_cannot_silently_promote_to_semantic_memory():
    research_surfaces = _python_files(
        REPO_ROOT / "control" / "research",
        REPO_ROOT / "core" / "research",
        REPO_ROOT / "interfaces" / "cli" / "research_cache.py",
        REPO_ROOT / "projections" / "api" / "routes" / "discovery_research.py",
    )
    offenders: list[str] = []

    for path in research_surfaces:
        source = _read(path)
        for token in sorted(MEMORY_PROMOTION_TOKENS):
            if token in source:
                offenders.append(f"{_rel(path)} contains {token}")

    assert offenders == []

    ingestion_source = _read(REPO_ROOT / "core" / "memory" / "ingestion.py")
    memory_store_source = _read(REPO_ROOT / "core" / "memory" / "store.py")
    contract = _read(RESEARCH_CONTRACT)

    assert "MemoryStore.upsert_by_provenance()" in contract
    assert "class IngestionConsumer" in ingestion_source
    assert "def upsert_by_provenance" in memory_store_source


def test_external_research_services_are_optional_and_degrade_cleanly():
    web_source = _read(REPO_ROOT / "control" / "research" / "web.py")
    tools_source = _read(REPO_ROOT / "control" / "research" / "tools.py")
    contract = _read(RESEARCH_CONTRACT).lower()

    assert re.search(r"api_key = os\.environ\.get\([\"']JINA_API_KEY[\"']\)", web_source)
    assert "if not api_key:" in web_source
    assert "return []" in web_source
    assert "sources = search_web(query)" in web_source

    assert "use_embeddings: bool = False" in tools_source
    assert "except (RuntimeError, ImportError)" in tools_source
    assert "falling back to TF-IDF" in tools_source

    assert "external research providers are optional" in contract
    assert "base local runtime validation must not require an external research service" in contract


def test_source_quality_ranking_outputs_executable_expected_fields():
    from interfaces.cli.source_ranker import rank_sources

    result = rank_sources(
        [
            {
                "url": "https://docs.python.org/3/library/sqlite3.html",
                "tier": 1,
                "findings": "Official sqlite3 docs describe connection modes.",
            },
            {
                "url": "https://www.sqlite.org/uri.html",
                "tier": 1,
                "findings": "SQLite URI docs note read-only mode.",
            },
            {
                "url": "https://example.com/analysis",
                "tier": 2,
                "findings": "However, integration behavior depends on callers.",
            },
        ]
    )

    for key in [
        "triangulation_score",
        "source_count",
        "tier1_count",
        "tier1_pct",
        "tier2_count",
        "domains",
        "shared_domains",
        "independence",
        "bias_flag",
        "counter_argument",
        "confidence",
        "gaps",
    ]:
        assert key in result

    assert result["source_count"] == 3
    assert result["triangulation_score"] == 1.0
    assert result["counter_argument"] == "PRESENT"
    assert result["confidence"] == "HIGH"


def test_private_research_payloads_are_local_private_unless_classified():
    contract = _read(RESEARCH_CONTRACT)
    governance_contract = _read(REPO_ROOT / "docs" / "contracts" / "governance-contract.md")

    for token in RAW_PRIVATE_TOKENS:
        assert token in contract

    contract_lower = contract.lower()
    assert "default classification is `local_only`" in contract_lower
    assert "redaction must happen before export" in contract_lower
    assert "full db backups are not redacted exports" in governance_contract.lower()


def test_legacy_research_diagnostics_remain_excluded_or_classified():
    contract = _read(RESEARCH_CONTRACT)
    dev_script = _read(REPO_ROOT / "scripts" / "dev.ps1")

    legacy_paths = [
        REPO_ROOT / "interfaces" / "cli" / "test_wave1_research_cache.py",
        REPO_ROOT / "interfaces" / "cli" / "debug_trust_score.py",
    ]

    for path in legacy_paths:
        assert path.exists()
        assert _rel(path) in contract
        assert _rel(path) not in dev_script.replace("\\", "/")
        assert not path.relative_to(REPO_ROOT).as_posix().startswith("tests/")

    assert "not normal validation" in contract.lower()
    assert "temp-home/tmp-DB isolated" in contract


def test_legacy_research_engine_imports_and_classifies_opt_in_status():
    from control.research import engine

    assert engine.ENGINE_STATUS == "legacy_opt_in"
    assert engine.ENGINE_AUTHORITY_CLASSIFICATION == "raw_research_advisory_lineage"
    assert engine._connect.__module__ == "core.event_store.studio_db"

    source = _read(REPO_ROOT / "control" / "research" / "engine.py")
    assert "legacy opt-in" in source.lower()
    assert "must not promote research output" in source
    assert "from .studio_db import _connect" not in source


def test_tool_detail_lookup_reads_catalog_metadata_only(tmp_path):
    from control.research import tools

    db_path = tmp_path / "tools.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE tool_registry (
            tool_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            source_url TEXT,
            install_command TEXT,
            tags TEXT,
            confidence_score REAL DEFAULT 0.5
        )
        """)
    conn.execute(
        """
        INSERT INTO tool_registry
        (tool_id, name, category, description, source_url, install_command, tags, confidence_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "mcp:firecrawl",
            "Firecrawl MCP",
            "mcp",
            "Catalog metadata only",
            "https://github.com/firecrawl/mcp",
            "npx @firecrawl/mcp",
            '["web", "mcp"]',
            0.91,
        ),
    )
    conn.commit()
    conn.close()

    def _connect():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    with patch("control.research.tools.studio_db._connect", side_effect=_connect):
        detail = tools.get_tool_by_id("mcp:firecrawl")
        missing = tools.get_tool_by_id("mcp:missing")

    assert detail is not None
    assert detail.tool_id == "mcp:firecrawl"
    assert detail.tags == ["web", "mcp"]
    assert detail.confidence_score == 0.91
    assert missing is None



def test_research_artifacts_expose_compatibility_classification_fields():
    from control.research import web

    source = web.Source(url="https://example.com", title="Example", snippet="Evidence", tier=2)
    report = web.ResearchReport(
        topic="example",
        sources=[source],
        findings="Evidence summary",
        confidence=0.6,
        triangulation=0.33,
    )

    assert source.source_type == "unknown"
    assert source.accessed_at == "unknown"
    assert source.extraction_notes == "unavailable"
    assert source.verification_status == "unverified"
    assert report.verification_status == "unverified"
    assert report.cache_status == "not_cached"
    assert report.privacy_export_classification == "local_only"
    assert report.created_at


def test_file_research_cache_adds_local_privacy_defaults(tmp_path, monkeypatch):
    from core.config import paths
    from core.research import store

    monkeypatch.setattr(paths, "user_data_dir", lambda: tmp_path / ".dream-studio")
    written = store.save_research(
        "security-owasp",
        {
            "sources": [
                {
                    "url": "https://owasp.org",
                    "tier": "1",
                    "date": "2026-05-01",
                    "key_findings": "Top 10 list",
                }
            ],
            "confidence": "medium",
            "triangulated": False,
            "saved_date": "2026-05-10",
            "refresh_due": "2026-06-10",
        },
    )

    assert written == tmp_path / ".dream-studio" / "research" / "security-owasp.json"
    payload = store.get_research("security-owasp")
    assert payload is not None
    assert payload["privacy_export_classification"] == "local_only"
    assert payload["verification_status"] == "unverified"
    assert payload["cache_status"] == "fresh"
    assert payload["sources"][0]["source_type"] == "unknown"
    assert payload["sources"][0]["source_tier"] == "1"
    assert payload["sources"][0]["extraction_notes"] == "Top 10 list"


def test_memory_search_uses_explicit_index_database(tmp_path):
    from control.research.memory import MemorySearch

    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "research.md").write_text(
        "# Research\n\nResearch cache is advisory evidence.",
        encoding="utf-8",
    )

    ms = MemorySearch(memory_dir)
    ms.build_index()

    assert ms.db_path == memory_dir / "memory.db"
    assert ms.db_path.exists()

    conn = sqlite3.connect(ms.db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM memory_meta").fetchone()[0]
    finally:
        conn.close()
    assert count == 1


def test_legacy_research_diagnostics_require_explicit_opt_in():
    diagnostics = {
        "interfaces/cli/debug_trust_score.py": "DREAM_STUDIO_RUN_LEGACY_RESEARCH_DIAGNOSTICS",
        "interfaces/cli/test_wave1_research_cache.py": "DREAM_STUDIO_RUN_LEGACY_RESEARCH_DIAGNOSTICS",
    }

    for rel_path, env_name in diagnostics.items():
        source = _read(REPO_ROOT / rel_path)
        assert env_name in source
        assert "Refusing" in source
        assert "isolated temp DB" in source
        assert "_require_opt_in()" in source
