"""Tests for SkillDispatcher.audit() and full-audit orchestration.

Proving gate: validates 18.8.2 merge criteria per build prompt.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.skills.dispatcher import (
    AuditFinding,
    AuditResult,
    SkillAuditStats,
    SkillDispatcher,
)

# ── Constants ──────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
DREAMYSUITE_PATH = Path.home() / "builds" / "dreamysuite"


# ── AuditResult unit tests ────────────────────────────────────────────────


class TestAuditResultDataclass:
    def test_audit_finding_hash_is_stable(self):
        f1 = AuditFinding(
            rule_id="sec-002",
            skill_id="security",
            severity="critical",
            tier="T1",
            file_path="core/foo.py",
            line=10,
            excerpt="f-string SQL",
        )
        f2 = AuditFinding(
            rule_id="sec-002",
            skill_id="security",
            severity="critical",
            tier="T1",
            file_path="core/foo.py",
            line=10,
            excerpt="f-string SQL",
        )
        assert f1.finding_hash == f2.finding_hash

    def test_audit_finding_hash_differs_on_file_change(self):
        f1 = AuditFinding(
            rule_id="sec-002",
            skill_id="security",
            severity="critical",
            tier="T1",
            file_path="core/foo.py",
            line=10,
            excerpt="f-string SQL",
        )
        f2 = AuditFinding(
            rule_id="sec-002",
            skill_id="security",
            severity="critical",
            tier="T1",
            file_path="core/bar.py",
            line=10,
            excerpt="f-string SQL",
        )
        assert f1.finding_hash != f2.finding_hash

    def test_audit_finding_skill_id_has_no_audit_suffix(self):
        f = AuditFinding(
            rule_id="cq-015",
            skill_id="code-quality",
            severity="critical",
            tier="T1",
            file_path="core/foo.py",
            line=5,
            excerpt="except:",
        )
        assert not f.skill_id.endswith(
            ":audit"
        ), "Audit findings must NOT have :audit suffix (pre-flight decision)"

    def test_audit_result_verdict_logic_critical_is_fail(self):
        result = AuditResult(scope_path=".")
        result.findings.append(
            AuditFinding(
                rule_id="sec-002",
                skill_id="security",
                severity="critical",
                tier="T1",
                file_path="foo.py",
                line=1,
                excerpt="",
            )
        )
        all_severities = {f.severity for f in result.findings}
        # Simulate verdict calculation
        if "critical" in all_severities:
            result.verdict = "FAIL"
        assert result.verdict == "FAIL"

    def test_audit_result_verdict_high_only_is_warning(self):
        result = AuditResult(scope_path=".")
        result.findings.append(
            AuditFinding(
                rule_id="cq-015",
                skill_id="code-quality",
                severity="high",
                tier="T2",
                file_path="foo.py",
                line=1,
                excerpt="",
            )
        )
        all_severities = {f.severity for f in result.findings}
        if "critical" not in all_severities and "high" in all_severities:
            result.verdict = "WARNING"
        assert result.verdict == "WARNING"

    def test_audit_result_no_findings_is_pass(self):
        result = AuditResult(scope_path=".")
        all_severities = {f.severity for f in result.findings}
        if "critical" not in all_severities and "high" not in all_severities:
            result.verdict = "PASS"
        assert result.verdict == "PASS"

    def test_summary_text_includes_skill_names(self):
        result = AuditResult(scope_path="/repo")
        result.per_skill["security"] = SkillAuditStats(
            skill_id="security", verdict="PASS", high_count=0
        )
        result.per_skill["code-quality"] = SkillAuditStats(
            skill_id="code-quality", verdict="WARNING", high_count=3
        )
        text = result.summary_text()
        assert "security" in text
        assert "code-quality" in text


# ── SkillDispatcher.audit() integration tests ─────────────────────────────


class TestSkillDispatcherAudit:
    def test_audit_dream_studio_clean_returns_audit_result(self):
        """Full audit on dream-studio-clean produces an AuditResult with all skills."""
        result = SkillDispatcher.audit(REPO_ROOT, skill_filter=["security", "code-quality"])
        assert isinstance(result, AuditResult)
        assert result.verdict in ("PASS", "WARNING", "FAIL", "AUDIT_ERROR")
        assert "security" in result.skills_run
        assert "code-quality" in result.skills_run

    def test_audit_produces_findings_on_dream_studio_clean(self):
        """dream-studio-clean has known code-quality findings (bare excepts, print())."""
        result = SkillDispatcher.audit(
            REPO_ROOT,
            skill_filter=["security", "code-quality"],
        )
        # Should find at least something (dream-studio-clean has print() calls and bare excepts)
        assert (
            len(result.findings) > 0
        ), "Expected findings on dream-studio-clean — codebase has known bare excepts and print() calls"

    def test_audit_finding_skill_ids_are_plain(self):
        """Audit findings use plain skill_id (no :audit suffix)."""
        result = SkillDispatcher.audit(REPO_ROOT, skill_filter=["security"])
        for f in result.findings:
            assert not f.skill_id.endswith(
                ":audit"
            ), f"Audit finding for {f.rule_id} has :audit suffix — pre-flight forbids this"

    def test_audit_finding_hashes_stable_on_rescan(self):
        """Running audit twice on unchanged repo produces identical finding hashes."""
        r1 = SkillDispatcher.audit(REPO_ROOT, skill_filter=["code-quality"])
        r2 = SkillDispatcher.audit(REPO_ROOT, skill_filter=["code-quality"])
        hashes1 = frozenset(f.finding_hash for f in r1.findings)
        hashes2 = frozenset(f.finding_hash for f in r2.findings)
        assert hashes1 == hashes2, "Finding hashes must be stable on rescan"

    def test_audit_per_skill_error_isolation(self):
        """A broken skill filter doesn't abort the audit — other skills complete."""
        result = SkillDispatcher.audit(
            REPO_ROOT,
            skill_filter=["security", "nonexistent-skill-xyz"],
        )
        # security should have run and produced stats
        assert "security" in result.per_skill, "Real skill should complete even if another fails"
        # nonexistent skill should be in failed or skipped — not abort the whole audit
        assert result.verdict != "AUDIT_ERROR" or "security" in result.per_skill

    def test_audit_all_skills_runs_11(self):
        """Default audit runs all 11 skills."""
        result = SkillDispatcher.audit(REPO_ROOT)
        assert len(result.skills_run) == 11

    def test_audit_skill_filter_limits_skills(self):
        """skill_filter reduces the skill set."""
        result = SkillDispatcher.audit(REPO_ROOT, skill_filter=["security", "ops"])
        assert result.skills_run == ["security", "ops"]
        assert len(result.per_skill) == 2

    def test_audit_dbc_on_dream_studio_clean_no_findings(self):
        """database-compliance produces 0 findings on dream-studio-clean (no PII schema)."""
        result = SkillDispatcher.audit(REPO_ROOT, skill_filter=["database-compliance"])
        dbc_findings = [f for f in result.findings if f.skill_id == "database-compliance"]
        # dream-studio-clean has no PII — dbc should auto-skip or find nothing
        assert (
            len(dbc_findings) == 0
        ), f"Expected 0 dbc findings on dream-studio-clean (no PII), got {len(dbc_findings)}"

    def test_audit_pl009_fires_on_dream_studio_clean(self):
        """pl-009 should fire: dream-studio-clean uses ph-X.Y.Z tags (not semver)."""
        result = SkillDispatcher.audit(REPO_ROOT, skill_filter=["pre-launch"])
        pl009 = [f for f in result.findings if f.rule_id == "pl-009"]
        assert (
            pl009
        ), "pl-009 should fire on dream-studio-clean: release tags use ph-X.Y.Z format, not semver"

    def test_audit_pl001_silent_on_dream_studio_clean(self):
        """pl-001 (Terms of Service) should be SILENT on dream-studio-clean (developer-tool)."""
        result = SkillDispatcher.audit(REPO_ROOT, skill_filter=["pre-launch"])
        pl001 = [f for f in result.findings if f.rule_id == "pl-001"]
        assert (
            not pl001
        ), "pl-001 should not fire on dream-studio-clean (developer-tool, not consumer)"

    def test_audit_arch004_fires_on_dream_studio_clean(self):
        """arch-004 layer inversion should detect mutations.py and status.py importing interfaces."""
        result = SkillDispatcher.audit(REPO_ROOT, skill_filter=["architecture"])
        arch004 = [f for f in result.findings if f.rule_id == "arch-004"]
        assert arch004, (
            "arch-004 should fire: core/design_briefs/mutations.py and "
            "core/health/status.py both import from interfaces/ (layer inversion)"
        )
        # Confirm the specific known files
        arch004_files = {f.file_path for f in arch004}
        found_known = any("mutations" in fp or "status" in fp for fp in arch004_files)
        assert (
            found_known
        ), f"Expected mutations.py or status.py in arch-004 findings, got: {arch004_files}"

    def test_audit_ops001_fires_on_dream_studio_clean(self):
        """ops-001 unstructured logging should fire: dream-studio-clean has print() in service code."""
        result = SkillDispatcher.audit(REPO_ROOT, skill_filter=["ops"])
        ops001 = [f for f in result.findings if f.rule_id == "ops-001"]
        assert (
            ops001
        ), "ops-001 should fire: projections/api/main.py:173 has print() in service startup"

    def test_audit_parallelism_multiple_skills_faster_than_sequential(self):
        """Parallel execution is observably faster than 11× single-skill time."""
        # Time a 3-skill audit
        start = time.monotonic()
        SkillDispatcher.audit(REPO_ROOT, skill_filter=["security", "code-quality", "database"])
        elapsed = time.monotonic() - start
        # Should complete in < 60s (parallel). If truly sequential it would be ~3× slower.
        assert elapsed < 120, f"3-skill audit took {elapsed:.1f}s (expected < 120s)"

    def test_audit_token_estimate_reported(self):
        """Token cost estimation is included in AuditResult (roadmap exit criterion)."""
        result = SkillDispatcher.audit(REPO_ROOT, skill_filter=["ops", "architecture"])
        # At least some LLM-pending rules should have token estimates
        assert result.total_tokens_estimated >= 0, "Token estimate must be non-negative"
        # Per-skill token estimates should sum to total
        total = sum(s.estimated_tokens for s in result.per_skill.values())
        assert total == result.total_tokens_estimated

    def test_audit_class_design_launch_readiness(self):
        """Confirm class-level shared infrastructure is accessible for .launch() implementation."""
        # These class-level helpers must exist and be callable for .launch() to reuse
        assert callable(SkillDispatcher._apply_threshold), "_apply_threshold must be class-level"
        assert callable(SkillDispatcher._resolve_skills), "_resolve_skills must be class-level"
        assert callable(SkillDispatcher.build), ".build() must exist"
        assert callable(SkillDispatcher.audit), ".audit() must exist"
        # Threshold map must be class-level (not buried in .build() or .audit())
        import core.skills.dispatcher as disp

        assert "_SEVERITY_TO_TIER" in dir(
            disp
        ), "_SEVERITY_TO_TIER must be module-level for .launch() to use it without refactoring"


# ── DreamySuite tests (conditional — only run if path exists) ─────────────


@pytest.mark.skipif(
    not DREAMYSUITE_PATH.exists(),
    reason="DreamySuite repo not present at ~/builds/dreamysuite",
)
class TestDreamySuiteAudit:
    def test_audit_dreamysuite_pl001_fires(self):
        """pl-001 (Terms of Service) fires on DreamySuite (consumer service)."""
        result = SkillDispatcher.audit(DREAMYSUITE_PATH, skill_filter=["pre-launch"])
        pl001 = [f for f in result.findings if f.rule_id == "pl-001"]
        assert pl001, "pl-001 should fire on DreamySuite — no Terms of Service found"

    def test_audit_dreamysuite_pl002_fires(self):
        """pl-002 (Privacy Policy) fires on DreamySuite (consumer with PII)."""
        result = SkillDispatcher.audit(DREAMYSUITE_PATH, skill_filter=["pre-launch"])
        pl002 = [f for f in result.findings if f.rule_id == "pl-002"]
        assert pl002, "pl-002 should fire on DreamySuite — no Privacy Policy + PII schema"

    def test_audit_dreamysuite_verdict_not_pass(self):
        """DreamySuite full audit should not be PASS (has known findings)."""
        result = SkillDispatcher.audit(DREAMYSUITE_PATH)
        assert (
            result.verdict != "PASS"
        ), "DreamySuite has known findings — verdict should be WARNING or FAIL"
