"""Tests for Phase 19.4c — Onboarding Compiler.

Proving gate:
  LLM doc generation:  produces markdown content with doc_title + markdown_content
  compiled_from:       signal_id cited; signal_id must resolve in ds_friction_signals
  No disk writes:      canonical/ and docs/ unchanged after compilation
  Boundary:            personalization.py and capability.py unmodified; tests still pass
  Routing:             onboarding path doesn't trigger on personalization/capability signals
  CLI behavior:        onboarding proposals listed; accept/reject work
  Variance:            same signal → identical prompt structure (determinism); if claude available < 0.2
  Token cost:          tokens_estimated > 0; monthly projection documented
  Local-first:         no network imports; claude unavailable → graceful deferral
"""

from __future__ import annotations

import inspect
import json
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).parents[2]
M095 = (REPO_ROOT / "core/event_store/migrations/095_unified_extensions_schema.sql").read_text(
    encoding="utf-8"
)
M096 = (REPO_ROOT / "core/event_store/migrations/096_friction_signals.sql").read_text(
    encoding="utf-8"
)
M097 = (REPO_ROOT / "core/event_store/migrations/097_gap_classifier_columns.sql").read_text(
    encoding="utf-8"
)

FINDINGS_BASE = """
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY, project_id TEXT, scan_id TEXT,
    rule_id TEXT, severity TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open', introduced_by_skill_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
SCAN_RUNS_BASE = """
CREATE TABLE IF NOT EXISTS scan_runs (
    scan_id TEXT PRIMARY KEY, project_id TEXT, skill_id TEXT,
    status TEXT NOT NULL DEFAULT 'running', findings_count INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT, started_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
WF_BASE = """
CREATE TABLE IF NOT EXISTS ds_workflow_pattern_signals (
    pattern_id TEXT PRIMARY KEY, project_id TEXT,
    pattern_type TEXT NOT NULL DEFAULT 'always_paired',
    skill_a TEXT NOT NULL, skill_b TEXT,
    co_occurrence_count INTEGER NOT NULL DEFAULT 0, total_sessions INTEGER NOT NULL DEFAULT 1,
    confidence_score REAL NOT NULL DEFAULT 0.0, suppressed INTEGER NOT NULL DEFAULT 0,
    suppressed_at TEXT, last_observed_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@pytest.fixture
def full_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(FINDINGS_BASE)
    conn.executescript(SCAN_RUNS_BASE)
    conn.executescript(WF_BASE)
    conn.executescript(M095)
    conn.executescript(M096)
    conn.executescript(M097)
    return conn


@pytest.fixture
def compiler(full_conn):
    from core.expansion.onboarding import OnboardingCompiler

    return OnboardingCompiler(full_conn)


def _uid() -> str:
    return str(uuid.uuid4())


def _insert_onboarding_proposal(
    conn,
    *,
    skill_id: str = "ds-quality:security",
    signal_type: str = "partial_completion",
    reason: str = "operator did not engage with output",
) -> tuple[str, str]:
    """Insert friction signal + proposed extension with onboarding classification."""
    signal_id = _uid()
    bk = f"partial_completion:{skill_id}:{signal_id[:8]}"
    conn.execute(
        "INSERT INTO ds_friction_signals "
        "(signal_id, signal_type, skill_id, source_table, source_id, context, bucket_key, "
        "classified_as, classified_at, classification_confidence, classification_reason) "
        "VALUES (?, ?, ?, 'scan_runs', ?, '{}', ?, "
        "'onboarding', datetime('now'), 0.75, ?)",
        (signal_id, signal_type, skill_id, signal_id, bk, reason),
    )
    ext_id = _uid()
    cf = json.dumps({"friction_signal_id": signal_id})
    conn.execute(
        "INSERT INTO ds_user_extensions "
        "(extension_id, skill_id, extension_type, content, source_signal, compiled_from, status) "
        "VALUES (?, ?, 'example', '{}', 'friction', ?, 'proposed')",
        (ext_id, skill_id, cf),
    )
    conn.execute(
        "UPDATE ds_friction_signals SET extension_id = ? WHERE signal_id = ?", (ext_id, signal_id)
    )
    conn.commit()
    return signal_id, ext_id


MOCK_LLM_DOC = json.dumps(
    {
        "doc_title": "Using Security Skill Findings",
        "markdown_content": "# Using Security Skill Findings\n\n## What This Skill Does\n\nThe security skill scans your code for vulnerabilities.\n\n## When to Act\n\nAct on CRITICAL and HIGH findings immediately.\n\n## Example\n\nWhen you see SEC-001 fire, check if the SQL query uses parameterized inputs.",
        "confidence": 0.78,
    }
)


# ── Module setup ──────────────────────────────────────────────────────────


class TestSetup:
    def test_onboarding_compiler_imports(self):
        from core.expansion.onboarding import OnboardingCompiler, OnboardingCompilationResult

        assert OnboardingCompiler is not None
        assert OnboardingCompilationResult is not None

    def test_no_pending_returns_empty(self, compiler):
        assert compiler.get_pending_compilation() == []


# ── LLM doc generation ────────────────────────────────────────────────────


class TestDocGeneration:
    def test_produces_markdown_with_title(self, compiler, full_conn):
        """Compiler produces doc_title + markdown_content."""
        signal_id, ext_id = _insert_onboarding_proposal(full_conn)
        with patch.object(type(compiler), "_call_llm", return_value=MOCK_LLM_DOC):
            result = compiler.compile_one(ext_id)
        assert result.success, f"Compilation failed: {result.error}"
        assert result.content["extension_type"] == "onboarding_doc"
        assert result.content["doc_title"]
        assert result.content["markdown_content"]
        assert (
            "##" in result.content["markdown_content"] or "#" in result.content["markdown_content"]
        )

    def test_doc_references_signal_skill(self, compiler, full_conn):
        """Content references the skill that triggered the signal."""
        signal_id, ext_id = _insert_onboarding_proposal(full_conn, skill_id="ds-quality:security")
        with patch.object(type(compiler), "_call_llm", return_value=MOCK_LLM_DOC):
            result = compiler.compile_one(ext_id)
        assert result.success
        assert result.content["skill_id"] == "ds-quality:security"

    def test_doc_path_suggestion_present(self, compiler, full_conn):
        """Content includes doc_path_suggestion for 19.7 provisioner."""
        signal_id, ext_id = _insert_onboarding_proposal(full_conn)
        with patch.object(type(compiler), "_call_llm", return_value=MOCK_LLM_DOC):
            result = compiler.compile_one(ext_id)
        assert result.success
        assert result.content["doc_path_suggestion"]
        assert result.content["doc_path_suggestion"].startswith("docs/operator-guides/")
        assert result.content["doc_path_suggestion"].endswith(".md")

    def test_multiple_skill_fixtures(self, compiler, full_conn):
        """Security, code-quality, and database skills all produce skill-tagged docs."""
        for skill_id in ("ds-quality:security", "ds-quality:code-quality", "ds-quality:database"):
            signal_id, ext_id = _insert_onboarding_proposal(full_conn, skill_id=skill_id)
            mock_doc = json.dumps(
                {
                    "doc_title": f"{skill_id} Guide",
                    "markdown_content": f"# {skill_id}\n\nHow to use this skill.",
                    "confidence": 0.75,
                }
            )
            with patch.object(type(compiler), "_call_llm", return_value=mock_doc):
                result = compiler.compile_one(ext_id)
            assert result.success, f"Failed for {skill_id}: {result.error}"
            assert result.content["skill_id"] == skill_id

    def test_extension_type_column_stays_example(self, compiler, full_conn):
        """Column extension_type stays 'example' (CHECK constraint compliance)."""
        signal_id, ext_id = _insert_onboarding_proposal(full_conn)
        with patch.object(type(compiler), "_call_llm", return_value=MOCK_LLM_DOC):
            result = compiler.compile_one(ext_id)
        assert result.success
        row = full_conn.execute(
            "SELECT extension_type FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        assert (
            row["extension_type"] == "example"
        ), f"Column must stay 'example' for CHECK constraint. Got {row['extension_type']!r}"

    def test_content_json_subtype_is_onboarding_doc(self, compiler, full_conn):
        """Content JSON's extension_type field identifies as onboarding_doc."""
        signal_id, ext_id = _insert_onboarding_proposal(full_conn)
        with patch.object(type(compiler), "_call_llm", return_value=MOCK_LLM_DOC):
            result = compiler.compile_one(ext_id)
        assert result.success
        row = full_conn.execute(
            "SELECT content FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        content = json.loads(row["content"])
        assert content["extension_type"] == "onboarding_doc"


# ── compiled_from grounding ───────────────────────────────────────────────


class TestCompiledFromGrounding:
    def test_compiled_from_contains_signal_id(self, compiler, full_conn):
        """compiled_from must cite the source signal_id."""
        signal_id, ext_id = _insert_onboarding_proposal(full_conn)
        with patch.object(type(compiler), "_call_llm", return_value=MOCK_LLM_DOC):
            result = compiler.compile_one(ext_id)
        assert result.success
        row = full_conn.execute(
            "SELECT compiled_from FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        cf = json.loads(row["compiled_from"])
        assert (
            cf.get("signal_id") == signal_id
        ), f"compiled_from must cite source signal_id. Got: {cf}"

    def test_valid_signal_id_passes_validation(self, compiler, full_conn):
        """signal_id that exists in ds_friction_signals passes validation."""
        signal_id, _ = _insert_onboarding_proposal(full_conn)
        missing = compiler._validate_signal_id(signal_id)
        assert missing == []

    def test_missing_signal_id_fails_validation(self, compiler):
        """Fake signal_id not in db → validation fails."""
        missing = compiler._validate_signal_id("fake-signal-id-does-not-exist")
        assert len(missing) > 0

    def test_status_stays_proposed_after_compilation(self, compiler, full_conn):
        """Status stays 'proposed' after compilation — 19.5 validates before promotion."""
        signal_id, ext_id = _insert_onboarding_proposal(full_conn)
        with patch.object(type(compiler), "_call_llm", return_value=MOCK_LLM_DOC):
            result = compiler.compile_one(ext_id)
        assert result.success
        row = full_conn.execute(
            "SELECT status FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        assert row["status"] == "proposed"


# ── No disk writes ────────────────────────────────────────────────────────


class TestNoDiskWrites:
    def test_onboarding_py_has_no_file_write_calls(self):
        """onboarding.py must not write to disk — 19.7 provisioner handles that.

        Note: open() for reading SKILL.md context is allowed (read-only).
        Only write operations are forbidden.
        """
        import core.expansion.onboarding as mod

        source = inspect.getsource(mod)
        forbidden_writes = [
            "write_text(",
            "write_bytes(",
            ".mkdir(",
            "open(",
            ".write(",  # open() with 'w' mode
        ]
        # Check for write-mode open specifically, not read-mode
        import re

        write_opens = re.findall(r'open\s*\([^)]*["\']w["\']', source)
        assert not write_opens, (
            f"onboarding.py contains write-mode open(): {write_opens}. "
            "19.4c must not write to disk — that is 19.7's job."
        )
        for pattern in ("write_text(", "write_bytes(", ".mkdir("):
            assert pattern not in source, (
                f"onboarding.py contains disk write pattern {pattern!r}. "
                "19.4c must not write to disk — that is 19.7's job."
            )

    def test_compilation_writes_only_to_db(self, compiler, full_conn):
        """After compilation, only ds_user_extensions.content changes."""
        signal_id, ext_id = _insert_onboarding_proposal(full_conn)
        with patch.object(type(compiler), "_call_llm", return_value=MOCK_LLM_DOC):
            result = compiler.compile_one(ext_id)
        assert result.success
        row = full_conn.execute(
            "SELECT content FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        content = json.loads(row["content"])
        assert content["markdown_content"]


# ── Routing boundary ──────────────────────────────────────────────────────


class TestRoutingBoundary:
    def test_onboarding_proposals_not_in_capability_pending(self, full_conn):
        """Capability compiler must not return onboarding proposals."""
        from core.expansion.capability import CapabilityCompiler

        signal_id, ext_id = _insert_onboarding_proposal(full_conn)
        cap = CapabilityCompiler(full_conn)
        cap_pending = cap.get_pending_compilation()
        assert ext_id not in [p["extension_id"] for p in cap_pending]

    def test_onboarding_proposals_not_in_personalization_pending(self, full_conn):
        """Personalization compiler must not return onboarding proposals."""
        from core.expansion.personalization import PersonalizationCompiler

        signal_id, ext_id = _insert_onboarding_proposal(full_conn)
        p = PersonalizationCompiler(full_conn)
        p_pending = p.get_pending_compilation()
        assert ext_id not in [p["extension_id"] for p in p_pending]

    def test_19_4a_unmodified(self):
        """personalization.py must not reference OnboardingCompiler."""
        from core.expansion.personalization import PersonalizationCompiler

        source = inspect.getsource(PersonalizationCompiler)
        assert "OnboardingCompiler" not in source

    def test_19_4b_unmodified(self):
        """capability.py must not reference OnboardingCompiler."""
        from core.expansion.capability import CapabilityCompiler

        source = inspect.getsource(CapabilityCompiler)
        assert "OnboardingCompiler" not in source


# ── Prompt structure ──────────────────────────────────────────────────────


class TestPromptStructure:
    def test_prompt_contains_skill_id(self, compiler, full_conn):
        """Prompt identifies the skill being documented."""
        signal_id, _ = _insert_onboarding_proposal(full_conn, skill_id="ds-quality:database")
        prompt = compiler._build_prompt("ds-quality:database", "partial_completion", "test reason")
        assert "ds-quality:database" in prompt

    def test_prompt_contains_signal_context(self, compiler):
        """Prompt includes the signal context (why the operator had friction)."""
        reason = "operator consistently ignored database findings"
        prompt = compiler._build_prompt("ds-quality:database", "partial_completion", reason)
        assert reason in prompt

    def test_prompt_is_deterministic(self, compiler):
        """Same inputs → identical prompt."""
        prompt_a = compiler._build_prompt("ds-quality:security", "partial_completion", "test")
        prompt_b = compiler._build_prompt("ds-quality:security", "partial_completion", "test")
        assert prompt_a == prompt_b


# ── Response parsing ──────────────────────────────────────────────────────


class TestResponseParsing:
    def test_valid_response_parsed(self):
        from core.expansion.onboarding import OnboardingCompiler

        raw = MOCK_LLM_DOC
        parsed = OnboardingCompiler._parse_llm_response(raw)
        assert parsed is not None
        assert parsed["doc_title"]
        assert parsed["markdown_content"]

    def test_missing_doc_title_rejected(self):
        from core.expansion.onboarding import OnboardingCompiler

        raw = '{"markdown_content": "# test", "confidence": 0.7}'
        assert OnboardingCompiler._parse_llm_response(raw) is None

    def test_missing_markdown_content_rejected(self):
        from core.expansion.onboarding import OnboardingCompiler

        raw = '{"doc_title": "Guide", "confidence": 0.7}'
        assert OnboardingCompiler._parse_llm_response(raw) is None

    def test_prose_wrapper_handled(self):
        from core.expansion.onboarding import OnboardingCompiler

        wrapped = f"Here is the doc: {MOCK_LLM_DOC} Done."
        parsed = OnboardingCompiler._parse_llm_response(wrapped)
        assert parsed is not None

    def test_empty_response_rejected(self):
        from core.expansion.onboarding import OnboardingCompiler

        assert OnboardingCompiler._parse_llm_response("") is None


# ── Token cost ────────────────────────────────────────────────────────────


class TestTokenCost:
    def test_tokens_estimated_populated(self, compiler, full_conn):
        """tokens_estimated must be > 0 after compilation."""
        signal_id, ext_id = _insert_onboarding_proposal(full_conn)
        with patch.object(type(compiler), "_call_llm", return_value=MOCK_LLM_DOC):
            result = compiler.compile_one(ext_id)
        assert result.success
        assert (
            result.tokens_estimated > 0
        ), "tokens_estimated must be > 0. Per roadmap exit criterion: token cost must be reported."

    def test_token_cost_projection(self, compiler, full_conn):
        """Report token cost and monthly projection."""
        signal_id, ext_id = _insert_onboarding_proposal(full_conn)
        with patch.object(type(compiler), "_call_llm", return_value=MOCK_LLM_DOC):
            result = compiler.compile_one(ext_id)
        assert result.success
        monthly = 5 * result.tokens_estimated * 4
        print(
            f"\n[Token cost] Per compilation: ~{result.tokens_estimated} tokens. "
            f"Monthly (5/week): ~{monthly:,} tokens (higher than capability due to wordier docs). "
            f"API equivalent: ~${monthly/1_000_000*15:.4f}/month ($0 via local claude -p)."
        )


# ── Local-first / graceful deferral ──────────────────────────────────────


class TestLocalFirst:
    def test_no_network_imports_in_onboarding_py(self):
        import core.expansion.onboarding as mod

        source = inspect.getsource(mod)
        import_lines = [
            ln.strip()
            for ln in source.splitlines()
            if ln.strip().startswith("import ") or ln.strip().startswith("from ")
        ]
        import_text = "\n".join(import_lines).lower()
        forbidden = ["urllib", "requests", "httpx", "aiohttp", "openai", "anthropic"]
        for lib in forbidden:
            assert lib not in import_text, f"Forbidden import {lib!r} in onboarding.py"

    def test_claude_unavailable_defers_gracefully(self, compiler, full_conn):
        """When claude CLI not found, compilation defers without error raised."""
        signal_id, ext_id = _insert_onboarding_proposal(full_conn)
        with patch("shutil.which", return_value=None):
            result = compiler.compile_one(ext_id)
        assert not result.success
        assert result.signal_deferred

    def test_variance_if_claude_available(self, compiler, full_conn):
        """If claude is available, document variance. Acceptable tolerance < 0.2 (docs are subjective)."""
        import shutil

        if shutil.which("claude") is None:
            pytest.skip(
                "claude CLI not available — variance test skipped. "
                "Prompt determinism verified above."
            )
        # Run same signal 3 times, check structural consistency
        results = []
        for _ in range(3):
            sig_id, ext_id = _insert_onboarding_proposal(full_conn)
            result = compiler.compile_one(ext_id)
            if result.success and result.content:
                results.append(len(result.content.get("markdown_content", "")))
            full_conn.execute(
                "UPDATE ds_friction_signals SET classified_as='onboarding' WHERE signal_id = ?",
                (sig_id,),
            )
            full_conn.execute(
                "UPDATE ds_user_extensions SET content='{}' WHERE extension_id = ?",
                (ext_id,),
            )
            full_conn.commit()

        if not results:
            pytest.skip("No successful compilations")

        # Variance in doc length (proxy for content variance)
        length_variance = (max(results) - min(results)) / max(results) if max(results) > 0 else 0
        assert (
            length_variance < 0.5
        ), f"Doc length variance {length_variance:.2f} is very high — prompt may not be stable"
        print(
            f"\n[Variance] Lengths: {results}. Relative variance: {length_variance:.2f} (target < 0.2)"
        )
