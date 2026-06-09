"""Tests for SkillDispatcher.launch() — launch-gate orchestration.

Proving gate: validates 18.8.x merge criteria per build prompt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.skills.dispatcher import (
    AuditResult,
    LaunchResult,
    SkillDispatcher,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DREAMYSUITE_PATH = Path.home() / "builds" / "dreamysuite"


# ── LaunchResult unit tests ───────────────────────────────────────────────


class TestLaunchResultDataclass:
    def test_launch_result_is_blocked_property(self):
        result = LaunchResult(
            verdict="LAUNCH_BLOCKED",
            service_type="consumer",
            audit_result=AuditResult(scope_path="."),
        )
        assert result.is_blocked
        assert not result.is_ready

    def test_launch_result_is_ready_property(self):
        result = LaunchResult(
            verdict="LAUNCH_READY",
            service_type="developer-tool",
            audit_result=AuditResult(scope_path="."),
        )
        assert result.is_ready
        assert not result.is_blocked

    def test_launch_result_carries_audit_result(self):
        audit = AuditResult(scope_path="/repo")
        result = LaunchResult(
            verdict="LAUNCH_READY",
            service_type="library",
            audit_result=audit,
        )
        assert result.audit_result is audit


# ── Escalation config tests ───────────────────────────────────────────────


class TestEscalationConfig:
    def test_escalation_config_exists_in_pre_launch_config(self):
        """launch_escalation section must be in pre-launch/config.yml (source of truth)."""
        import yaml

        config_path = (
            REPO_ROOT / "canonical" / "skills" / "quality" / "modes" / "pre-launch" / "config.yml"
        )
        cfg = yaml.safe_load(config_path.read_text())
        assert "launch_escalation" in cfg, (
            "launch_escalation section missing from pre-launch/config.yml — "
            "escalation config must live in the skill, not hardcoded in dispatcher"
        )

    def test_escalation_config_has_all_four_service_types(self):
        import yaml

        config_path = (
            REPO_ROOT / "canonical" / "skills" / "quality" / "modes" / "pre-launch" / "config.yml"
        )
        cfg = yaml.safe_load(config_path.read_text())
        escalation = cfg["launch_escalation"]
        for st in ("consumer", "developer-tool", "internal-service", "library"):
            assert st in escalation, f"service_type '{st}' missing from launch_escalation"

    def test_pl001_blocked_for_consumer_silent_for_developer_tool(self):
        """pl-001 must block on consumer, be silent on developer-tool."""
        import yaml

        config_path = (
            REPO_ROOT / "canonical" / "skills" / "quality" / "modes" / "pre-launch" / "config.yml"
        )
        cfg = yaml.safe_load(config_path.read_text())
        escalation = cfg["launch_escalation"]
        assert "pl-001" in escalation["consumer"]["blocked_rules"]
        assert "pl-001" in escalation["developer-tool"]["silent_rules"]


# ── SkillDispatcher.launch() integration tests ────────────────────────────


class TestSkillDispatcherLaunch:
    def test_launch_dream_studio_clean_returns_launch_result(self):
        result = SkillDispatcher.launch(REPO_ROOT)
        assert isinstance(result, LaunchResult)
        assert result.verdict in ("LAUNCH_READY", "LAUNCH_WARNING", "LAUNCH_BLOCKED")

    def test_launch_dream_studio_clean_service_type_is_developer_tool(self):
        """dream-studio-clean must be detected as developer-tool (has interfaces/cli/)."""
        result = SkillDispatcher.launch(REPO_ROOT)
        assert result.service_type == "developer-tool", (
            f"Expected developer-tool, got {result.service_type}. "
            "interfaces/cli/ is the primary CLI signal."
        )

    def test_launch_dream_studio_clean_pl001_not_in_blocking(self):
        """pl-001 must NOT block on developer-tool (silent rule)."""
        result = SkillDispatcher.launch(REPO_ROOT)
        pl001_blocking = [f for f in result.blocking_findings if f.rule_id == "pl-001"]
        assert not pl001_blocking, (
            "pl-001 (Terms of Service) should be SILENT on developer-tool, "
            f"but appeared in blocking: {pl001_blocking}"
        )

    def test_launch_dream_studio_clean_pl009_blocks(self):
        """pl-009 (non-semver tags) must LAUNCH_BLOCKED on developer-tool."""
        result = SkillDispatcher.launch(REPO_ROOT)
        pl009_blocking = [f for f in result.blocking_findings if f.rule_id == "pl-009"]
        assert pl009_blocking, (
            "pl-009 should block: dream-studio-clean uses ph-X.Y.Z tags (not semver). "
            f"blocking_findings has: {[f.rule_id for f in result.blocking_findings]}"
        )

    def test_launch_dream_studio_clean_is_blocked(self):
        """dream-studio-clean should be LAUNCH_BLOCKED (pl-009 non-semver tags)."""
        result = SkillDispatcher.launch(REPO_ROOT)
        assert (
            result.verdict == "LAUNCH_BLOCKED"
        ), f"Expected LAUNCH_BLOCKED (pl-009), got {result.verdict}"

    def test_launch_audit_result_populated(self):
        """.launch() must populate audit_result with full audit findings."""
        result = SkillDispatcher.launch(REPO_ROOT)
        assert isinstance(result.audit_result, AuditResult)
        assert (
            len(result.audit_result.findings) > 0
        ), "audit_result.findings should be populated — .launch() calls .audit() internally"

    def test_launch_audit_findings_match_standalone_audit(self):
        """Findings from .launch() underlying audit == findings from .audit() standalone."""
        audit_standalone = SkillDispatcher.audit(REPO_ROOT)
        launch_result = SkillDispatcher.launch(REPO_ROOT)
        standalone_hashes = frozenset(f.finding_hash for f in audit_standalone.findings)
        launch_audit_hashes = frozenset(f.finding_hash for f in launch_result.audit_result.findings)
        assert (
            standalone_hashes == launch_audit_hashes
        ), ".launch()'s underlying audit must produce the same findings as .audit() standalone"

    def test_launch_service_type_override_consumer_on_developer_tool(self):
        """Override developer-tool as consumer → pl-001 becomes blocking."""
        result = SkillDispatcher.launch(REPO_ROOT, service_type="consumer")
        assert result.service_type == "consumer"
        pl001_blocking = [f for f in result.blocking_findings if f.rule_id == "pl-001"]
        assert pl001_blocking, (
            "With service_type=consumer override, pl-001 should block "
            "(no Terms of Service in dream-studio-clean)"
        )

    def test_launch_token_cost_reported(self):
        """Token cost must be in LaunchResult (roadmap exit criterion)."""
        result = SkillDispatcher.launch(REPO_ROOT)
        assert result.tokens_consumed >= 0
        # tokens_consumed should equal audit_result.total_tokens_estimated
        assert result.tokens_consumed == result.audit_result.total_tokens_estimated

    def test_launch_summary_includes_verdict_and_service_type(self):
        result = SkillDispatcher.launch(REPO_ROOT)
        assert result.verdict in result.launch_summary
        assert result.service_type in result.launch_summary

    def test_launch_class_method_exists(self):
        assert callable(SkillDispatcher.launch)
        assert callable(SkillDispatcher.build)
        assert callable(SkillDispatcher.audit)

    def test_no_regression_build_method_still_works(self):
        """Existing .build() must not regress after .launch() addition.
        CLEAN or ADVISORY_ONLY are both acceptable — T3 advisories (missing docstring)
        don't indicate a regression, build still returns code.
        """
        code = "def add(a, b): return a + b\n"
        result = SkillDispatcher.build(code, "python", {})
        assert result.verdict in (
            "CLEAN",
            "ADVISORY_ONLY",
        ), f"Expected CLEAN or ADVISORY_ONLY (T3 advisory is not a regression), got {result.verdict}"
        # No T1 blocking findings — that WOULD be a regression
        assert not result.t1_blocking, f"Unexpected T1 findings on clean code: {result.t1_blocking}"

    def test_launch_library_override_pl001_becomes_silent(self):
        """Override DreamySuite as library → pl-001/002 become silent."""
        if not DREAMYSUITE_PATH.exists():
            pytest.skip("DreamySuite not found")
        result = SkillDispatcher.launch(DREAMYSUITE_PATH, service_type="library")
        pl001_blocking = [f for f in result.blocking_findings if f.rule_id == "pl-001"]
        pl002_blocking = [f for f in result.blocking_findings if f.rule_id == "pl-002"]
        assert (
            not pl001_blocking
        ), "With service_type=library, pl-001 should be SILENT (in silent_rules)"
        assert (
            not pl002_blocking
        ), "With service_type=library, pl-002 should be SILENT (in silent_rules)"

    def test_launch_library_override_pl009_still_blocks(self):
        """Override as library → pl-009 (semver) still blocks."""
        if not DREAMYSUITE_PATH.exists():
            pytest.skip("DreamySuite not found")
        # Use dream-studio-clean (has non-semver tags) with library override
        result = SkillDispatcher.launch(REPO_ROOT, service_type="library")
        pl009_blocking = [f for f in result.blocking_findings if f.rule_id == "pl-009"]
        assert pl009_blocking, (
            "pl-009 should still block with service_type=library: "
            "libraries need semver regardless of consumer/library type"
        )


# ── DreamySuite tests (conditional) ──────────────────────────────────────


@pytest.mark.skipif(
    not DREAMYSUITE_PATH.exists(),
    reason="DreamySuite not present at ~/builds/dreamysuite",
)
class TestDreamySuiteLaunch:
    def test_launch_dreamysuite_is_consumer(self):
        result = SkillDispatcher.launch(DREAMYSUITE_PATH)
        assert result.service_type == "consumer"

    def test_launch_dreamysuite_is_blocked(self):
        result = SkillDispatcher.launch(DREAMYSUITE_PATH)
        assert result.verdict == "LAUNCH_BLOCKED"

    def test_launch_dreamysuite_pl001_blocks(self):
        result = SkillDispatcher.launch(DREAMYSUITE_PATH)
        pl001 = [f for f in result.blocking_findings if f.rule_id == "pl-001"]
        assert pl001, "pl-001 (ToS) should block on DreamySuite consumer service"

    def test_launch_dreamysuite_pl002_blocks(self):
        result = SkillDispatcher.launch(DREAMYSUITE_PATH)
        pl002 = [f for f in result.blocking_findings if f.rule_id == "pl-002"]
        assert pl002, "pl-002 (Privacy Policy) should block on DreamySuite consumer service"

    def test_launch_dreamysuite_library_override_removes_legal_blocks(self):
        """Overriding DreamySuite as library removes pl-001/002 from blocking."""
        result_consumer = SkillDispatcher.launch(DREAMYSUITE_PATH, service_type="consumer")
        result_library = SkillDispatcher.launch(DREAMYSUITE_PATH, service_type="library")
        consumer_pl001 = [f for f in result_consumer.blocking_findings if f.rule_id == "pl-001"]
        library_pl001 = [f for f in result_library.blocking_findings if f.rule_id == "pl-001"]
        assert consumer_pl001, "pl-001 should block as consumer"
        assert not library_pl001, "pl-001 should NOT block as library (service_type override works)"
