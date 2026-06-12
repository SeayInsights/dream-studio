"""Tests for pulse health degradation on red full-ci conclusion (WO de7e86cd)."""

from __future__ import annotations

from unittest.mock import patch


class TestFullCiHealthDegradation:
    def test_failure_conclusion_degrades_healthy_to_degraded(self):
        """When full-ci on main returns 'failure', HEALTHY → DEGRADED."""
        from interfaces.cli.pulse_collector import generate_pulse

        with (
            patch("interfaces.cli.pulse_collector._github_repo", return_value="org/repo"),
            patch("interfaces.cli.pulse_collector.check_stale_branches", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_overdue_milestones", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_open_prs", return_value=[]),
            patch(
                "interfaces.cli.pulse_collector.check_ci_status",
                return_value="full-ci: failure",
            ),
            patch(
                "interfaces.cli.pulse_collector.check_full_ci_on_main",
                return_value="failure",
            ),
            patch("interfaces.cli.pulse_collector.check_open_escalations", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_stale_agents", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_pending_drafts", return_value=[]),
            patch("interfaces.cli.pulse_collector.auto_archive_stale_drafts", return_value=0),
            patch("interfaces.cli.pulse_collector._run_memory_maintenance"),
            patch("interfaces.cli.pulse_collector.check_corrections_growth", return_value=(0, "")),
            patch("interfaces.cli.pulse_collector.collect_memory_stats", return_value={}),
            patch(
                "interfaces.cli.pulse_collector._get_skill_health",
                return_value=([], ""),
            ),
            patch("interfaces.cli.pulse_collector._update_skill_metadata"),
            patch("core.eval.friction.count_degraded_skills", return_value=0),
        ):
            _report, stats = generate_pulse()

        assert stats["health"] != "HEALTHY", (
            "health must not be HEALTHY when full-ci conclusion is 'failure'"
        )
        assert stats["full_ci_conclusion"] == "failure"

    def test_success_conclusion_does_not_degrade_health(self):
        """When full-ci on main returns 'success', health remains HEALTHY with no other issues."""
        from interfaces.cli.pulse_collector import generate_pulse

        with (
            patch("interfaces.cli.pulse_collector._github_repo", return_value="org/repo"),
            patch("interfaces.cli.pulse_collector.check_stale_branches", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_overdue_milestones", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_open_prs", return_value=[]),
            patch(
                "interfaces.cli.pulse_collector.check_ci_status",
                return_value="full-ci: success",
            ),
            patch(
                "interfaces.cli.pulse_collector.check_full_ci_on_main",
                return_value="success",
            ),
            patch("interfaces.cli.pulse_collector.check_open_escalations", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_stale_agents", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_pending_drafts", return_value=[]),
            patch("interfaces.cli.pulse_collector.auto_archive_stale_drafts", return_value=0),
            patch("interfaces.cli.pulse_collector._run_memory_maintenance"),
            patch("interfaces.cli.pulse_collector.check_corrections_growth", return_value=(0, "")),
            patch("interfaces.cli.pulse_collector.collect_memory_stats", return_value={}),
            patch(
                "interfaces.cli.pulse_collector._get_skill_health",
                return_value=([], ""),
            ),
            patch("interfaces.cli.pulse_collector._update_skill_metadata"),
            patch("core.eval.friction.count_degraded_skills", return_value=0),
        ):
            _report, stats = generate_pulse()

        assert stats["health"] == "HEALTHY"
        assert stats["full_ci_conclusion"] == "success"

    def test_failure_conclusion_does_not_mask_existing_issues(self):
        """When full-ci fails AND other issues exist (health already ATTENTION), health stays ATTENTION."""
        from interfaces.cli.pulse_collector import generate_pulse

        with (
            patch("interfaces.cli.pulse_collector._github_repo", return_value="org/repo"),
            patch(
                "interfaces.cli.pulse_collector.check_stale_branches",
                return_value=["old-branch (10d stale)"],
            ),
            patch("interfaces.cli.pulse_collector.check_overdue_milestones", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_open_prs", return_value=[]),
            patch(
                "interfaces.cli.pulse_collector.check_ci_status",
                return_value="full-ci: failure",
            ),
            patch(
                "interfaces.cli.pulse_collector.check_full_ci_on_main",
                return_value="failure",
            ),
            patch("interfaces.cli.pulse_collector.check_open_escalations", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_stale_agents", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_pending_drafts", return_value=[]),
            patch("interfaces.cli.pulse_collector.auto_archive_stale_drafts", return_value=0),
            patch("interfaces.cli.pulse_collector._run_memory_maintenance"),
            patch("interfaces.cli.pulse_collector.check_corrections_growth", return_value=(0, "")),
            patch("interfaces.cli.pulse_collector.collect_memory_stats", return_value={}),
            patch(
                "interfaces.cli.pulse_collector._get_skill_health",
                return_value=([], ""),
            ),
            patch("interfaces.cli.pulse_collector._update_skill_metadata"),
            patch("core.eval.friction.count_degraded_skills", return_value=0),
        ):
            _report, stats = generate_pulse()

        assert stats["health"] != "HEALTHY"

    def test_report_flags_full_ci_failure_in_ci_section(self):
        """Report CI Status section contains a warning when full-ci conclusion is 'failure'."""
        from interfaces.cli.pulse_collector import generate_pulse

        with (
            patch("interfaces.cli.pulse_collector._github_repo", return_value="org/repo"),
            patch("interfaces.cli.pulse_collector.check_stale_branches", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_overdue_milestones", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_open_prs", return_value=[]),
            patch(
                "interfaces.cli.pulse_collector.check_ci_status",
                return_value="full-ci: failure",
            ),
            patch(
                "interfaces.cli.pulse_collector.check_full_ci_on_main",
                return_value="failure",
            ),
            patch("interfaces.cli.pulse_collector.check_open_escalations", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_stale_agents", return_value=[]),
            patch("interfaces.cli.pulse_collector.check_pending_drafts", return_value=[]),
            patch("interfaces.cli.pulse_collector.auto_archive_stale_drafts", return_value=0),
            patch("interfaces.cli.pulse_collector._run_memory_maintenance"),
            patch("interfaces.cli.pulse_collector.check_corrections_growth", return_value=(0, "")),
            patch("interfaces.cli.pulse_collector.collect_memory_stats", return_value={}),
            patch(
                "interfaces.cli.pulse_collector._get_skill_health",
                return_value=([], ""),
            ),
            patch("interfaces.cli.pulse_collector._update_skill_metadata"),
            patch("core.eval.friction.count_degraded_skills", return_value=0),
        ):
            report, _stats = generate_pulse()

        assert "full-ci" in report
        assert "failure" in report
