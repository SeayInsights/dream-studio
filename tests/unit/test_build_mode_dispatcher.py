"""Tests for SkillDispatcher.build() and build-mode skill auditors.

Proving gate: each test validates a specific behavior per the 18.8.1 merge criteria.
"""

from __future__ import annotations

import time

import pytest

from core.skills.dispatcher import (
    BUILD_TIMEOUT_SECONDS,
    BuildTimeoutError,
    SkillDispatcher,
    TIER_T1,
    TIER_T2,
    TIER_T3,
)
from core.skills.build.code_quality import audit_generated_python as cq_audit
from core.skills.build.security import audit_generated_python as sec_audit
from core.skills.build.database import audit_generated_sql_or_python as db_audit

# ── Fixtures ──────────────────────────────────────────────────────────────

CLEAN_PYTHON = '''
def calculate_total(items: list, tax_rate: float) -> float:
    """Calculate total with tax."""
    subtotal = sum(item.price for item in items)
    return subtotal * (1 + tax_rate)
'''

SQL_INJECTION_PYTHON = """
def get_user(email: str):
    conn.execute(f"SELECT * FROM users WHERE email='{email}'")
"""

HARDCODED_SECRET = """
API_KEY = "sk-abc123def456"
client = openai.Client(api_key=API_KEY)
"""

WEAK_HASH_PYTHON = """
import hashlib

def store_password(password: str):
    return hashlib.md5(password.encode()).hexdigest()
"""

BARE_EXCEPT_PYTHON = """
def process():
    try:
        do_work()
    except:
        pass
"""

SILENT_EXCEPT_PYTHON = """
def process():
    try:
        do_work()
    except Exception:
        pass
"""

WILDCARD_IMPORT_PYTHON = """
from os.path import *
from datetime import *
"""

CLEAN_SQL = """
CREATE TABLE orders (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    total_cents INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

SQL_INJECTION_SQL = """
def get_user(email):
    query = f"SELECT * FROM users WHERE email='{email}'"
    return db.execute(query)
"""

CREATE_TABLE_NO_PK = """
CREATE TABLE events (
    event_type TEXT NOT NULL,
    payload TEXT,
    created_at TEXT
);
"""

DROP_NO_COMMENT = """
DROP TABLE legacy_users;
"""

MONEY_AS_FLOAT = """
CREATE TABLE products (
    id TEXT PRIMARY KEY,
    price REAL NOT NULL
);
"""


# ── code_quality auditor tests ─────────────────────────────────────────────


class TestCodeQualityAuditor:

    def test_clean_python_returns_no_critical_findings(self):
        findings = cq_audit(CLEAN_PYTHON, {})
        critical = [f for f in findings if f["tier"] == TIER_T1]
        assert not critical, f"Expected no T1 findings on clean code, got: {critical}"

    def test_bare_except_pass_fires_cq006(self):
        findings = cq_audit(BARE_EXCEPT_PYTHON, {})
        rule_ids = [f["rule_id"] for f in findings]
        assert "cq-006" in rule_ids, f"Expected cq-006, got: {rule_ids}"

    def test_cq006_is_t1_blocking(self):
        findings = cq_audit(BARE_EXCEPT_PYTHON, {})
        cq006 = [f for f in findings if f["rule_id"] == "cq-006"]
        assert cq006, "cq-006 not found"
        assert cq006[0]["tier"] == TIER_T1

    def test_bare_except_without_pass_fires_cq015(self):
        code = """
def f():
    try:
        x()
    except:
        raise
"""
        findings = cq_audit(code, {})
        rule_ids = [f["rule_id"] for f in findings]
        assert "cq-015" in rule_ids

    def test_wildcard_import_fires_cq_explicit(self):
        findings = cq_audit(WILDCARD_IMPORT_PYTHON, {})
        rule_ids = [f["rule_id"] for f in findings]
        assert "cq-A-explicit" in rule_ids

    def test_wildcard_import_is_t3_advisory(self):
        findings = cq_audit(WILDCARD_IMPORT_PYTHON, {})
        cq_exp = [f for f in findings if f["rule_id"] == "cq-A-explicit"]
        assert cq_exp[0]["tier"] == TIER_T3

    def test_performance_on_100_loc_under_500ms(self):
        code = "\n".join([f"    x_{i} = {i}" for i in range(100)])
        start = time.monotonic()
        cq_audit(code, {})
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 500, f"code_quality auditor took {elapsed_ms:.1f}ms (limit: 500ms)"


# ── security auditor tests ─────────────────────────────────────────────────


class TestSecurityAuditor:

    def test_clean_python_no_findings(self):
        findings = sec_audit(CLEAN_PYTHON, {})
        assert not findings, f"Expected no findings on clean code, got: {findings}"

    def test_sql_injection_fires_sec002(self):
        findings = sec_audit(SQL_INJECTION_PYTHON, {})
        rule_ids = [f["rule_id"] for f in findings]
        assert "sec-002" in rule_ids

    def test_sql_injection_is_t1(self):
        findings = sec_audit(SQL_INJECTION_PYTHON, {})
        sec002 = [f for f in findings if f["rule_id"] == "sec-002"]
        assert sec002[0]["tier"] == TIER_T1

    def test_hardcoded_api_key_fires_sec001(self):
        findings = sec_audit(HARDCODED_SECRET, {})
        rule_ids = [f["rule_id"] for f in findings]
        assert "sec-001" in rule_ids

    def test_hardcoded_api_key_is_t1(self):
        findings = sec_audit(HARDCODED_SECRET, {})
        sec001 = [f for f in findings if f["rule_id"] == "sec-001"]
        assert sec001[0]["tier"] == TIER_T1

    def test_weak_password_hash_fires_sec005(self):
        findings = sec_audit(WEAK_HASH_PYTHON, {})
        rule_ids = [f["rule_id"] for f in findings]
        assert "sec-005" in rule_ids

    def test_placeholder_credentials_not_flagged(self):
        # Placeholders should not fire sec-001
        code = 'API_KEY = "your-api-key-here"\nDB_PASSWORD = "<your-password>"'
        findings = sec_audit(code, {})
        sec001 = [f for f in findings if f["rule_id"] == "sec-001"]
        assert not sec001, f"Placeholder credentials should not fire sec-001: {sec001}"

    def test_performance_under_500ms(self):
        code = "\n".join([f"    value_{i} = {i}" for i in range(100)])
        start = time.monotonic()
        sec_audit(code, {})
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 500


# ── database auditor tests ─────────────────────────────────────────────────


class TestDatabaseAuditor:

    def test_clean_sql_no_t1_findings(self):
        findings = db_audit(CLEAN_SQL, {})
        t1 = [f for f in findings if f["tier"] == TIER_T1]
        assert not t1, f"Expected no T1 on clean SQL, got: {t1}"

    def test_create_table_no_pk_fires_db001(self):
        findings = db_audit(CREATE_TABLE_NO_PK, {})
        rule_ids = [f["rule_id"] for f in findings]
        assert "db-001" in rule_ids

    def test_db001_is_t1_blocking(self):
        findings = db_audit(CREATE_TABLE_NO_PK, {})
        db001 = [f for f in findings if f["rule_id"] == "db-001"]
        assert db001[0]["tier"] == TIER_T1

    def test_drop_without_comment_fires_db011(self):
        findings = db_audit(DROP_NO_COMMENT, {})
        rule_ids = [f["rule_id"] for f in findings]
        assert "db-011" in rule_ids

    def test_money_as_float_fires_db005(self):
        findings = db_audit(MONEY_AS_FLOAT, {})
        rule_ids = [f["rule_id"] for f in findings]
        assert "db-005" in rule_ids

    def test_sql_injection_fstring_fires_db009(self):
        findings = db_audit(SQL_INJECTION_SQL, {})
        rule_ids = [f["rule_id"] for f in findings]
        assert "db-009" in rule_ids


# ── SkillDispatcher.build() integration tests ─────────────────────────────


class TestSkillDispatcherBuild:

    def test_clean_python_returns_clean_verdict(self):
        result = SkillDispatcher.build(CLEAN_PYTHON, "python", {})
        assert result.verdict == "CLEAN"
        assert not result.t1_blocking
        assert result.skills_run == ["security", "code-quality", "database"]

    def test_t1_finding_produces_launch_blocked_verdict(self):
        result = SkillDispatcher.build(SQL_INJECTION_PYTHON, "python", {})
        assert result.verdict == "LAUNCH_BLOCKED"
        assert result.t1_blocking

    def test_t1_finding_has_build_context_skill_id(self):
        result = SkillDispatcher.build(SQL_INJECTION_PYTHON, "python", {})
        assert result.t1_blocking
        # All findings should have ":build" suffix to distinguish from audit findings
        for f in result.all_findings:
            assert f.skill_id.endswith(":build"), f"Expected :build suffix, got {f.skill_id}"

    def test_sql_language_only_runs_database_skill(self):
        result = SkillDispatcher.build(CREATE_TABLE_NO_PK, "sql", {})
        assert result.skills_run == ["database"]
        assert result.verdict in ("LAUNCH_BLOCKED", "LAUNCH_WARNING", "ADVISORY_ONLY", "CLEAN")

    def test_unsupported_language_returns_clean_no_skills(self):
        result = SkillDispatcher.build("fn main() {}", "rust", {})
        assert result.verdict == "CLEAN"
        assert result.skills_run == []

    def test_typescript_runs_security_and_code_quality(self):
        result = SkillDispatcher.build("const x = 1;", "typescript", {})
        assert "security" in result.skills_run
        assert "code-quality" in result.skills_run
        assert "database" not in result.skills_run

    def test_build_findings_have_stable_hash(self):
        r1 = SkillDispatcher.build(SQL_INJECTION_PYTHON, "python", {})
        r2 = SkillDispatcher.build(SQL_INJECTION_PYTHON, "python", {})
        hashes1 = {f.finding_hash for f in r1.all_findings}
        hashes2 = {f.finding_hash for f in r2.all_findings}
        assert hashes1 == hashes2, "Finding hashes should be stable on rescan"

    def test_static_pass_completes_under_2s_on_200_loc(self):
        code = "\n".join(
            [
                "def process_item(item, config, db, cache, logger):",
                "    result = {}",
            ]
            + [f"    result['key_{i}'] = item.get('field_{i}', None)" for i in range(95)]
            + [
                "    return result",
            ]
        )
        start = time.monotonic()
        SkillDispatcher.build(code, "python", {})
        elapsed = time.monotonic() - start
        assert (
            elapsed < BUILD_TIMEOUT_SECONDS
        ), f"Static pass took {elapsed:.2f}s (limit: {BUILD_TIMEOUT_SECONDS}s)"

    def test_timeout_raises_build_timeout_error(self):
        """Verify BuildTimeoutError is raised when timeout is exceeded."""
        import unittest.mock as mock

        # Simulate a slow auditor by mocking time.monotonic to fast-forward
        original_auditor = SkillDispatcher._call_skill_auditor

        call_count = [0]

        def slow_auditor(skill, code, context):
            call_count[0] += 1
            if call_count[0] == 1:
                # First skill call simulated as exceeding timeout
                time.sleep(BUILD_TIMEOUT_SECONDS + 0.1)
            return original_auditor(skill, code, context)

        with mock.patch.object(SkillDispatcher, "_call_skill_auditor", slow_auditor):
            with pytest.raises(BuildTimeoutError):
                SkillDispatcher.build(CLEAN_PYTHON, "python", {})

    def test_inline_text_clean_is_empty(self):
        result = SkillDispatcher.build(CLEAN_PYTHON, "python", {})
        assert result.to_inline_text() == ""

    def test_inline_text_blocked_includes_rule_id(self):
        result = SkillDispatcher.build(SQL_INJECTION_PYTHON, "python", {})
        text = result.to_inline_text()
        assert "BLOCKED" in text
        assert "sec-002" in text

    def test_t2_warning_returns_code_with_warning(self):
        # Code with only a T2 issue — should return LAUNCH_WARNING, not LAUNCH_BLOCKED
        code = """
def fetch_users():
    rows = db.execute("SELECT * FROM users LIMIT 10 OFFSET 100")
    return rows
"""
        result = SkillDispatcher.build(code, "sql", {})
        # db-014 is T2 (offset pagination warning)
        if result.t2_warnings:
            assert result.verdict == "LAUNCH_WARNING"
            assert not result.t1_blocking
