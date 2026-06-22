"""Real feedback engine - NO synthetic scores, ONLY real execution signals."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime, timezone

from core.config.database import transaction, get_connection
from .ci_collector import CIResult
from .github_adapter import GitHubExecutionResult


@dataclass
class RealActionFeedback:
    """Feedback from REAL execution only.

    STRICT RULE: All metrics derived from actual execution or marked as unknown.
    """

    execution_id: str
    action_id: str
    execution_status: str  # created | failed | unknown
    test_status: str  # passed | failed | unknown
    ci_status: str  # passed | failed | unknown

    # Test results (REAL or marked unknown)
    test_count: int = 0
    passed_count: int = 0
    failed_count: int = 0

    # CI results (REAL or marked unknown)
    ci_checks: int = 0
    ci_checks_passed: int = 0

    # Code changes (REAL from git diff)
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0

    # Build status (REAL or unknown)
    build_success: Optional[bool] = None

    # Overall effectiveness (DERIVED from real signals ONLY)
    effectiveness_score: float = 0.0
    confirmed_effective: bool = False

    # Root cause analysis (REAL error messages only)
    root_cause: Optional[str] = None

    # Availability markers
    tests_available: bool = False
    ci_available: bool = False

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RealFeedbackEngine:
    """Evaluate action effectiveness using ONLY real execution signals.

    ZERO synthetic scoring. ZERO simulation.
    """

    def evaluate_real_execution(
        self, action_id: str, execution_result: GitHubExecutionResult, ci_result: CIResult
    ) -> RealActionFeedback:
        """Evaluate effectiveness from real execution.

        Args:
            action_id: Action identifier
            execution_result: GitHub execution result
            ci_result: CI/test result

        Returns:
            RealActionFeedback with ONLY real signals
        """
        feedback = RealActionFeedback(
            execution_id=execution_result.commit_sha or "unknown",
            action_id=action_id,
            execution_status=execution_result.status,
            test_status="unknown",
            ci_status="unknown",
        )

        # 1. Execution status
        if execution_result.status != "created":
            feedback.root_cause = execution_result.error_message
            feedback.confirmed_effective = False
            return feedback

        # 2. Test results (REAL ONLY)
        feedback.test_status = ci_result.status
        feedback.test_count = ci_result.test_count
        feedback.passed_count = ci_result.passed_count
        feedback.failed_count = ci_result.failed_count
        feedback.tests_available = ci_result.tests_run

        # 3. CI status (REAL ONLY)
        feedback.ci_status = ci_result.status
        feedback.ci_checks = len(ci_result.ci_checks)
        feedback.ci_checks_passed = sum(
            1 for c in ci_result.ci_checks if c.get("conclusion") == "success"
        )
        feedback.ci_available = ci_result.ci_available

        # 4. Code changes (REAL from git)
        if execution_result.diff_stats:
            feedback.files_changed = execution_result.diff_stats.files_changed
            feedback.insertions = execution_result.diff_stats.insertions
            feedback.deletions = execution_result.diff_stats.deletions

        # 5. Build status (REAL ONLY)
        feedback.build_success = ci_result.build_success

        # 6. Compute effectiveness (DERIVED from real signals ONLY)
        feedback.effectiveness_score = self._compute_real_effectiveness(feedback)

        # 7. Confirm effectiveness (STRICT threshold)
        feedback.confirmed_effective = (
            feedback.effectiveness_score > 0.7
            and feedback.test_status == "passed"
            and feedback.execution_status == "created"
        )

        # 8. Root cause if failed
        if feedback.test_status == "failed":
            if ci_result.failed_tests:
                feedback.root_cause = f"{len(ci_result.failed_tests)} tests failed: " + ", ".join(
                    t.test_name for t in ci_result.failed_tests[:3]
                )
            else:
                feedback.root_cause = "Tests failed (details unavailable)"

        return feedback

    def _compute_real_effectiveness(self, feedback: RealActionFeedback) -> float:
        """Compute effectiveness from REAL signals ONLY.

        NO synthetic scoring. NO placeholders.

        Args:
            feedback: RealActionFeedback with real signals

        Returns:
            Effectiveness score (0.0-1.0) or 0.0 if insufficient data
        """
        score = 0.0
        signals_available = 0

        # Signal 1: Test pass rate (50% weight if available)
        if feedback.tests_available and feedback.test_count > 0:
            test_pass_rate = feedback.passed_count / feedback.test_count
            score += test_pass_rate * 0.5
            signals_available += 1

        # Signal 2: CI status (30% weight if available)
        if feedback.ci_available:
            if feedback.ci_status == "passed":
                score += 0.3
                signals_available += 1
            elif feedback.ci_status == "failed":
                # Actively bad
                score += 0.0
                signals_available += 1

        # Signal 3: Build success (20% weight if available)
        if feedback.build_success is not None:
            if feedback.build_success:
                score += 0.2
                signals_available += 1
            else:
                score += 0.0
                signals_available += 1

        # If no real signals available, score = 0.0 (UNKNOWN, not synthetic)
        if signals_available == 0:
            return 0.0

        # Normalize by available signals
        # If only some signals available, scale up proportionally
        if signals_available == 1:
            # Only 1 signal - less confidence, cap at 0.6
            return min(score, 0.6)
        if signals_available == 2:
            # 2 signals - moderate confidence, cap at 0.8
            return min(score, 0.8)
        # All signals available - full confidence
        return score

    def store_real_feedback(self, feedback: RealActionFeedback):
        """Store real feedback in database.

        Args:
            feedback: RealActionFeedback to store
        """
        try:
            with transaction() as conn:
                # Ensure table exists
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS real_action_feedback (
                        execution_id TEXT,
                        action_id TEXT,
                        execution_status TEXT,
                        test_status TEXT,
                        test_count INTEGER,
                        passed_count INTEGER,
                        failed_count INTEGER,
                        ci_status TEXT,
                        ci_checks INTEGER,
                        ci_checks_passed INTEGER,
                        files_changed INTEGER,
                        insertions INTEGER,
                        deletions INTEGER,
                        build_success INTEGER,
                        effectiveness_score REAL,
                        confirmed_effective INTEGER,
                        root_cause TEXT,
                        tests_available INTEGER,
                        ci_available INTEGER,
                        timestamp TEXT
                    )
                """)

                # Store feedback
                conn.execute(
                    """INSERT INTO real_action_feedback
                       (execution_id, action_id, execution_status,
                        test_status, test_count, passed_count, failed_count,
                        ci_status, ci_checks, ci_checks_passed,
                        files_changed, insertions, deletions,
                        build_success, effectiveness_score, confirmed_effective,
                        root_cause, tests_available, ci_available, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        feedback.execution_id,
                        feedback.action_id,
                        feedback.execution_status,
                        feedback.test_status,
                        feedback.test_count,
                        feedback.passed_count,
                        feedback.failed_count,
                        feedback.ci_status,
                        feedback.ci_checks,
                        feedback.ci_checks_passed,
                        feedback.files_changed,
                        feedback.insertions,
                        feedback.deletions,
                        (
                            1
                            if feedback.build_success
                            else 0 if feedback.build_success is not None else None
                        ),
                        feedback.effectiveness_score,
                        1 if feedback.confirmed_effective else 0,
                        feedback.root_cause,
                        1 if feedback.tests_available else 0,
                        1 if feedback.ci_available else 0,
                        feedback.timestamp,
                    ),
                )

        except Exception as e:
            print(f"Warning: Failed to store real feedback: {e}")

    def get_effectiveness_statistics(self) -> Dict[str, float]:
        """Get aggregate effectiveness statistics from real feedback.

        Returns:
            Statistics dict with real execution data
        """
        try:
            with get_connection() as conn:
                result = conn.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(confirmed_effective) as effective,
                        AVG(effectiveness_score) as avg_score,
                        SUM(CASE WHEN test_status = 'passed' THEN 1 ELSE 0 END) as tests_passed,
                        SUM(CASE WHEN ci_status = 'passed' THEN 1 ELSE 0 END) as ci_passed,
                        SUM(CASE WHEN tests_available = 1 THEN 1 ELSE 0 END) as with_tests,
                        SUM(CASE WHEN ci_available = 1 THEN 1 ELSE 0 END) as with_ci
                    FROM real_action_feedback
                """).fetchone()

                if not result or result[0] == 0:
                    return {
                        "total_executions": 0,
                        "effective_count": 0,
                        "avg_effectiveness": 0.0,
                        "test_pass_rate": 0.0,
                        "ci_pass_rate": 0.0,
                        "tests_coverage": 0.0,
                        "ci_coverage": 0.0,
                    }

                total, effective, avg_score, tests_passed, ci_passed, with_tests, with_ci = result

                return {
                    "total_executions": total,
                    "effective_count": effective or 0,
                    "avg_effectiveness": avg_score or 0.0,
                    "test_pass_rate": tests_passed / with_tests if with_tests > 0 else 0.0,
                    "ci_pass_rate": ci_passed / with_ci if with_ci > 0 else 0.0,
                    "tests_coverage": with_tests / total if total > 0 else 0.0,
                    "ci_coverage": with_ci / total if total > 0 else 0.0,
                }

        except Exception:
            return {
                "total_executions": 0,
                "effective_count": 0,
                "avg_effectiveness": 0.0,
                "test_pass_rate": 0.0,
                "ci_pass_rate": 0.0,
                "tests_coverage": 0.0,
                "ci_coverage": 0.0,
            }
