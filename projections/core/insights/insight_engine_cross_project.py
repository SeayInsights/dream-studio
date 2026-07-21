"""InsightEngine mixin: cross-project and operational correlation insights.

WO-GF-READINESS-INSIGHTS: split from ``projections/core/insights/insight_engine.py``.
Methods extracted verbatim onto a mixin; ``InsightEngine`` inherits it.
"""

from typing import Any


class _CrossProjectMixin:
    def generate_cross_project_insights(
        self, project_metrics: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Identify patterns across multiple projects

        Args:
            project_metrics: Dict mapping project_id → project metrics

        Returns:
            List of cross-project insights
        """
        insights = []

        if len(project_metrics) < 2:
            return insights  # Need at least 2 projects for cross-project analysis

        # Pattern 1: Consistent skill performance across projects
        skill_success_by_project = {}
        for project_id, metrics in project_metrics.items():
            if "skills" in metrics:
                for skill_name, skill_data in metrics["skills"].items():
                    if skill_name not in skill_success_by_project:
                        skill_success_by_project[skill_name] = []
                    success_rate = skill_data.get("success_rate", 0)
                    skill_success_by_project[skill_name].append(
                        {"project": project_id, "success_rate": success_rate}
                    )

        # Identify skills that perform consistently well across projects
        for skill_name, project_data in skill_success_by_project.items():
            if len(project_data) >= 2:  # Used in at least 2 projects
                avg_success = sum(p["success_rate"] for p in project_data) / len(project_data)
                if avg_success > 0.9:
                    insights.append(
                        {
                            "category": "cross_project_strength",
                            "title": f"{skill_name} performs consistently across projects",
                            "description": (
                                f"{skill_name} maintains {avg_success*100:.0f}% success rate across "
                                f"{len(project_data)} projects. This skill is reliable and portable."
                            ),
                            "impact": "medium",
                            "evidence": {
                                "projects": [p["project"] for p in project_data],
                                "avg_success_rate": avg_success,
                            },
                        }
                    )

        # Pattern 2: Project velocity comparison
        session_counts = {
            pid: pm.get("sessions", {}).get("total_sessions", 0)
            for pid, pm in project_metrics.items()
        }
        if session_counts:
            most_active = max(session_counts, key=session_counts.get)
            least_active = min(session_counts, key=session_counts.get)

            if session_counts[most_active] > session_counts[least_active] * 5:
                insights.append(
                    {
                        "category": "cross_project_velocity",
                        "title": f"Activity concentrated in {most_active}",
                        "description": (
                            f"{most_active} has {session_counts[most_active]} sessions while "
                            f"{least_active} has only {session_counts[least_active]}. Consider whether "
                            f"less-active projects need attention or can be archived."
                        ),
                        "impact": "low",
                        "evidence": {"session_distribution": session_counts},
                    }
                )

        # Pattern 3: Operational health correlation
        # (will be populated by operational correlation feature)

        return insights

    def generate_operational_insights(
        self, pulse_data: list[dict[str, Any]], session_data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Correlate operational health (pulse snapshots) with session outcomes

        Args:
            pulse_data: List of pulse snapshots with health scores, CI status, etc.
            session_data: List of sessions with outcomes, duration, etc.

        Returns:
            List of operational correlation insights
        """
        insights = []

        if not pulse_data or not session_data:
            return insights

        # Group sessions by date
        from collections import defaultdict

        sessions_by_date = defaultdict(list)
        for session in session_data:
            if "started_at" in session and session["started_at"]:
                date = session["started_at"][:10]  # Extract YYYY-MM-DD
                sessions_by_date[date].append(session)

        # Group pulse snapshots by date
        pulse_by_date = {}
        for pulse in pulse_data:
            if "snapshot_at" in pulse and pulse["snapshot_at"]:
                date = pulse["snapshot_at"][:10]
                pulse_by_date[date] = pulse

        # Correlate pulse health with session success rate
        correlations = []
        for date, sessions in sessions_by_date.items():
            if date in pulse_by_date:
                pulse = pulse_by_date[date]
                health_score = pulse.get("health_score", 100)
                ci_status = pulse.get("ci_status", "unknown")

                success_count = sum(1 for s in sessions if s.get("outcome") == "completed")
                total = len(sessions)
                success_rate = success_count / total if total > 0 else 0

                correlations.append(
                    {
                        "date": date,
                        "health_score": health_score,
                        "ci_status": ci_status,
                        "session_success_rate": success_rate,
                        "total_sessions": total,
                    }
                )

        # Identify patterns
        if len(correlations) >= 3:
            # Pattern: Low health → low session success
            low_health_days = [c for c in correlations if c["health_score"] < 80]
            if low_health_days:
                avg_success_low_health = sum(
                    c["session_success_rate"] for c in low_health_days
                ) / len(low_health_days)
                high_health_days = [c for c in correlations if c["health_score"] >= 95]
                if high_health_days:
                    avg_success_high_health = sum(
                        c["session_success_rate"] for c in high_health_days
                    ) / len(high_health_days)

                    if avg_success_high_health - avg_success_low_health > 0.15:
                        insights.append(
                            {
                                "category": "operational_correlation",
                                "title": "Health score impacts session success",
                                "description": (
                                    f"Sessions on days with health score <80 have {avg_success_low_health*100:.0f}% success rate, "
                                    f"compared to {avg_success_high_health*100:.0f}% on days with health ≥95. "
                                    f"Low health correlates with {(avg_success_high_health - avg_success_low_health)*100:.0f}% worse outcomes."
                                ),
                                "impact": "high",
                                "evidence": {
                                    "low_health_days": len(low_health_days),
                                    "high_health_days": len(high_health_days),
                                    "success_diff": avg_success_high_health
                                    - avg_success_low_health,
                                },
                                "recommended_action": "Monitor health proactively — investigate drops before starting critical work",
                            }
                        )

            # Pattern: CI failures → session interruptions
            ci_fail_days = [c for c in correlations if c["ci_status"] == "failing"]
            if len(ci_fail_days) >= 2:
                avg_sessions_on_fail_days = sum(c["total_sessions"] for c in ci_fail_days) / len(
                    ci_fail_days
                )
                ci_pass_days = [c for c in correlations if c["ci_status"] == "passing"]
                if ci_pass_days:
                    avg_sessions_on_pass_days = sum(
                        c["total_sessions"] for c in ci_pass_days
                    ) / len(ci_pass_days)

                    if avg_sessions_on_pass_days > avg_sessions_on_fail_days * 1.3:
                        insights.append(
                            {
                                "category": "operational_correlation",
                                "title": "CI failures reduce session productivity",
                                "description": (
                                    f"On days when CI is failing, average {avg_sessions_on_fail_days:.1f} sessions. "
                                    f"When CI passes, average {avg_sessions_on_pass_days:.1f} sessions. "
                                    f"CI issues may be blocking work or requiring context switches."
                                ),
                                "impact": "medium",
                                "evidence": {
                                    "ci_fail_days": len(ci_fail_days),
                                    "ci_pass_days": len(ci_pass_days),
                                    "session_diff": avg_sessions_on_pass_days
                                    - avg_sessions_on_fail_days,
                                },
                                "recommended_action": "Prioritize CI fixes — they have measurable productivity impact",
                            }
                        )

        return insights
