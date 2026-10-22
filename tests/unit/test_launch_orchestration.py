"""Tests for SkillDispatcher.launch() — launch-gate orchestration.

Proving gate: validates 18.8.x merge criteria per build prompt.
"""

from __future__ import annotations

from pathlib import Path

from core.skills.dispatcher import (
    AuditResult,
    LaunchResult,
    SkillDispatcher,
)
from tests.helpers.fixture_projects import consumer_service, developer_tool

REPO_ROOT = Path(__file__).resolve().parents[2]


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
            REPO_ROOT / "canonical" / "skills" / "release" / "modes" / "pre-launch" / "config.yml"
        )
        cfg = yaml.safe_load(config_path.read_text())
        assert "launch_escalation" in cfg, (
            "launch_escalation section missing from pre-launch/config.yml — "
            "escalation config must live in the skill, not hardcoded in dispatcher"
        )

    def test_escalation_config_has_all_four_service_types(self):
        import yaml

        config_path = (
            REPO_ROOT / "canonical" / "skills" / "release" / "modes" / "pre-launch" / "config.yml"
        )
        cfg = yaml.safe_load(config_path.read_text())
        escalation = cfg["launch_escalation"]
        for st in ("consumer", "developer-tool", "internal-service", "library"):
            assert st in escalation, f"service_type '{st}' missing from launch_escalation"

    def test_pl001_blocked_for_consumer_silent_for_developer_tool(self):
        """pl-001 must block on consumer, be silent on developer-tool."""
        import yaml

        config_path = (
            REPO_ROOT / "canonical" / "skills" / "release" / "modes" / "pre-launch" / "config.yml"
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

    # pl-009 reads the release tags of the repository it is pointed at, so it is tested
    # against repositories built here with the tags the case needs. These used to launch
    # against THIS checkout and assert it "uses ph-X.Y.Z tags": whatever tags the clone
    # held decided the result (a clone made with --no-tags, or one that later gained a
    # semver tag, gave a different answer to the same code).

    def test_launch_non_semver_tag_blocks(self, tmp_path):
        """pl-009 (non-semver tags) must block a developer-tool."""
        project = developer_tool(tmp_path / "tool", tags=("ph-1.2.3",))
        result = SkillDispatcher.launch(project)
        pl009_blocking = [f for f in result.blocking_findings if f.rule_id == "pl-009"]
        assert pl009_blocking, (
            "pl-009 should block a project whose newest tag is ph-X.Y.Z (not semver). "
            f"blocking_findings has: {[f.rule_id for f in result.blocking_findings]}"
        )
        assert "ph-1.2.3" in pl009_blocking[0].excerpt

    def test_launch_no_tags_blocks(self, tmp_path):
        """pl-009 also fires when there are no tags: no versioning is established."""
        project = developer_tool(tmp_path / "tool")
        result = SkillDispatcher.launch(project)
        assert [f for f in result.blocking_findings if f.rule_id == "pl-009"]

    def test_launch_semver_tag_does_not_block_on_pl009(self, tmp_path):
        """The control: a vX.Y.Z tag clears pl-009, so the two cases above can fail."""
        project = developer_tool(tmp_path / "tool", tags=("v1.2.3",))
        result = SkillDispatcher.launch(project)
        assert not [f for f in result.blocking_findings if f.rule_id == "pl-009"]

    def test_launch_non_semver_tag_is_blocked(self, tmp_path):
        """A developer-tool with only a non-semver tag is LAUNCH_BLOCKED on pl-009."""
        project = developer_tool(tmp_path / "tool", tags=("ph-1.2.3",))
        result = SkillDispatcher.launch(project)
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

    def test_launch_library_override_pl001_becomes_silent(self, tmp_path):
        """Override a consumer service as library → pl-001/002 become silent."""
        project = consumer_service(tmp_path / "svc")
        result = SkillDispatcher.launch(project, service_type="library")
        pl001_blocking = [f for f in result.blocking_findings if f.rule_id == "pl-001"]
        pl002_blocking = [f for f in result.blocking_findings if f.rule_id == "pl-002"]
        assert (
            not pl001_blocking
        ), "With service_type=library, pl-001 should be SILENT (in silent_rules)"
        assert (
            not pl002_blocking
        ), "With service_type=library, pl-002 should be SILENT (in silent_rules)"

    def test_launch_library_override_pl009_still_blocks(self, tmp_path):
        """Override as library → pl-009 (semver) still blocks.

        Built from a repository with no semver tag, not from "this checkout has none": the
        test used to depend on the clone's tag list and on a sibling repository existing.
        """
        project = developer_tool(tmp_path / "tool", tags=("ph-1.2.3",))
        result = SkillDispatcher.launch(project, service_type="library")
        pl009_blocking = [f for f in result.blocking_findings if f.rule_id == "pl-009"]
        assert pl009_blocking, (
            "pl-009 should still block with service_type=library: "
            "libraries need semver regardless of consumer/library type"
        )


# ── Consumer-service tests (a fixture project, not a sibling repository) ──
#
# These used to launch against ``~/builds/dreamysuite`` and skip when it was absent, so the
# consumer-service blocking rules were untested on every machine but one and the result
# changed whenever that project did.


class TestConsumerServiceLaunch:
    def test_launch_consumer_service_is_consumer(self, tmp_path):
        result = SkillDispatcher.launch(consumer_service(tmp_path / "svc"))
        assert result.service_type == "consumer"

    def test_a_schema_that_stores_an_email_alone_makes_a_consumer_service(self, tmp_path):
        project = consumer_service(tmp_path / "svc", web_ui=False)
        assert SkillDispatcher.launch(project).service_type == "consumer"

    def test_a_web_ui_alone_makes_a_consumer_service(self, tmp_path):
        project = consumer_service(tmp_path / "svc", stores_email=False)
        assert SkillDispatcher.launch(project).service_type == "consumer"

    def test_neither_signal_is_not_a_consumer_service(self, tmp_path):
        """The control for the two above: with no web UI and no personal data in the schema the
        project is not inferred to be a consumer service, so they are not vacuous."""
        project = consumer_service(tmp_path / "svc", web_ui=False, stores_email=False)
        assert SkillDispatcher.launch(project).service_type != "consumer"

    def test_launch_consumer_service_is_blocked(self, tmp_path):
        result = SkillDispatcher.launch(consumer_service(tmp_path / "svc"))
        assert result.verdict == "LAUNCH_BLOCKED"

    def test_launch_consumer_service_pl001_blocks(self, tmp_path):
        result = SkillDispatcher.launch(consumer_service(tmp_path / "svc"))
        pl001 = [f for f in result.blocking_findings if f.rule_id == "pl-001"]
        assert pl001, "pl-001 (ToS) should block a consumer service with no terms"

    def test_launch_consumer_service_pl002_blocks(self, tmp_path):
        result = SkillDispatcher.launch(consumer_service(tmp_path / "svc"))
        pl002 = [f for f in result.blocking_findings if f.rule_id == "pl-002"]
        assert pl002, "pl-002 (Privacy Policy) should block a consumer service with no policy"

    def test_launch_consumer_service_with_legal_documents_does_not_block_on_them(self, tmp_path):
        """The control: with both documents present neither legal rule blocks."""
        result = SkillDispatcher.launch(consumer_service(tmp_path / "svc", legal_documents=True))
        blocking = {f.rule_id for f in result.blocking_findings}
        assert not blocking & {"pl-001", "pl-002"}, sorted(blocking)

    def test_launch_consumer_service_library_override_removes_legal_blocks(self, tmp_path):
        """Overriding a consumer service as library removes pl-001/002 from blocking."""
        project = consumer_service(tmp_path / "svc")
        result_consumer = SkillDispatcher.launch(project, service_type="consumer")
        result_library = SkillDispatcher.launch(project, service_type="library")
        consumer_pl001 = [f for f in result_consumer.blocking_findings if f.rule_id == "pl-001"]
        library_pl001 = [f for f in result_library.blocking_findings if f.rule_id == "pl-001"]
        assert consumer_pl001, "pl-001 should block as consumer"
        assert not library_pl001, "pl-001 should NOT block as library (service_type override works)"
