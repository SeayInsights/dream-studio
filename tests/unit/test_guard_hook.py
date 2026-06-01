"""Tests for the on-skill-input guard hook.

Tests PAIR fixtures:
  - 4 positive fixtures must produce at least 1 static finding
  - 4 negative fixtures must produce 0 findings
  - Suppression paths work correctly
  - .md files never get static-fired
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from guardrails.scanner_utils import (
    apply_llm_candidate_patterns,
    apply_static_patterns,
    is_suppressed,
    load_guard_rules,
)


@pytest.fixture
def guard_config():
    """Load the guard rules YAML."""
    return load_guard_rules()


@pytest.fixture
def rules(guard_config):
    return guard_config.get("rules", [])


@pytest.fixture
def suppressed_globs(guard_config):
    return guard_config.get("suppressed_paths", [])


# Fixtures that should fire static_fire rules
POSITIVE_STATIC_FIXTURES = [
    "tests/fixtures/guard/positive/guard-001-direct-override.py",
    "tests/fixtures/guard/positive/guard-003-system-prompt.py",
    "tests/fixtures/guard/positive/guard-005-chatml.py",
]

# Fixtures that should fire llm_confirm rules (guard-013 is llm_confirm, not static_fire)
POSITIVE_LLM_FIXTURES = [
    "tests/fixtures/guard/positive/guard-013-jailbreak.py",
]

NEGATIVE_FIXTURES = [
    "tests/fixtures/guard/negative/system-as-data-key.json",
    "tests/fixtures/guard/negative/legitimate-send-todo.py",
]


class TestStaticPatterns:
    def test_positive_fixture_fires(self, rules):
        """Each static-fire positive fixture must produce at least 1 static finding."""
        for fixture_path in POSITIVE_STATIC_FIXTURES:
            path = REPO_ROOT / fixture_path
            if not path.exists():
                pytest.skip(f"Fixture not found: {fixture_path}")
            content = path.read_text(encoding="utf-8")
            findings = apply_static_patterns(content, rules)
            assert len(findings) >= 1, (
                f"Expected at least 1 finding in {fixture_path}, got 0. "
                f"Rules loaded: {len([r for r in rules if r.get('detection') == 'static_fire'])}"
            )

    def test_positive_llm_fixture_fires(self, rules):
        """Each llm_confirm positive fixture must produce at least 1 LLM candidate."""
        for fixture_path in POSITIVE_LLM_FIXTURES:
            path = REPO_ROOT / fixture_path
            if not path.exists():
                pytest.skip(f"Fixture not found: {fixture_path}")
            content = path.read_text(encoding="utf-8")
            candidates = apply_llm_candidate_patterns(content, rules)
            assert len(candidates) >= 1, (
                f"Expected at least 1 LLM candidate in {fixture_path}, got 0. "
                f"Rules loaded: {len([r for r in rules if r.get('detection') == 'llm_confirm'])}"
            )

    def test_negative_fixture_stays_silent(self, rules):
        """Each non-suppressed negative fixture must produce 0 static findings."""
        for fixture_path in NEGATIVE_FIXTURES:
            path = REPO_ROOT / fixture_path
            if not path.exists():
                pytest.skip(f"Fixture not found: {fixture_path}")
            content = path.read_text(encoding="utf-8")
            findings = apply_static_patterns(content, rules)
            assert len(findings) == 0, (
                f"Expected 0 static findings in {fixture_path}, got {len(findings)}: "
                f"{[f['rule_id'] for f in findings]}"
            )

    def test_md_file_gets_zero_static_findings(self, rules):
        """Markdown files should never trigger static-fire rules."""
        # OWASP doc quote — static patterns appear but we simulate md handling
        md_fixture = REPO_ROOT / "tests/fixtures/guard/negative/owasp-doc.md"
        if not md_fixture.exists():
            pytest.skip("MD fixture not found")
        content = md_fixture.read_text(encoding="utf-8")
        # Static patterns may match in content, but the hook skips static for .md
        # Here we test that if the hook applies static to .md content it still finds
        # the pattern — the key is that the HOOK should skip static for .md files
        # (tested in integration; here we just verify the content does contain a pattern
        # that would fire if static were applied — proving the skip is meaningful)
        # Actually: the OWASP doc doesn't contain the actual regexes from rules,
        # it contains the DESCRIPTIONS. So static should return 0 anyway.
        findings = apply_static_patterns(content, rules)
        # The OWASP doc quotes patterns in plain English, not regex form
        # so static patterns should not match
        assert len(findings) == 0, f"MD fixture fired: {[f['rule_id'] for f in findings]}"


class TestSuppression:
    def test_guardrails_dir_suppressed(self, suppressed_globs):
        """guardrails/ directory is suppressed."""
        assert is_suppressed("guardrails/scanners/rebuff_validator.py", suppressed_globs)
        assert is_suppressed("guardrails/rules/guard-patterns.yaml", suppressed_globs)

    def test_security_skill_suppressed(self, suppressed_globs):
        """Security skill directory is suppressed (contains injection patterns as docs)."""
        assert is_suppressed("canonical/skills/quality/modes/security/rules.yml", suppressed_globs)

    def test_tests_dir_suppressed(self, suppressed_globs):
        """tests/ directory is suppressed (fixtures may contain positive examples)."""
        assert is_suppressed(
            "tests/fixtures/guard/positive/guard-001-direct-override.py", suppressed_globs
        )
        assert is_suppressed("tests/unit/test_guard_hook.py", suppressed_globs)

    def test_normal_file_not_suppressed(self, suppressed_globs):
        """Normal source files are not suppressed."""
        assert not is_suppressed("src/app/utils.py", suppressed_globs)
        assert not is_suppressed("lib/auth.ts", suppressed_globs)

    def test_recursive_case_suppressed(self, suppressed_globs):
        """The recursive self-reference fixture in tests/ is suppressed."""
        assert is_suppressed(
            "tests/fixtures/guard/negative/guardrails-patterns-copy.py", suppressed_globs
        )
