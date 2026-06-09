"""CI signal collector - ingest real test and CI results.

UNIFIED (2026-05-07): Now emits decisions AND events to track test execution.
"""

from __future__ import annotations
import subprocess
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timezone

from core.decisions import emit_decision
from canonical.events.envelope import CanonicalEventEnvelope
from canonical.events.types import EventType as CanonicalEventType
from canonical.events.redactor import redact_file_path, redact_bash_command
from emitters.shared.spool_writer import write_envelopes


@dataclass
class TestResult:
    """Individual test result."""

    test_name: str
    status: str  # passed | failed | skipped
    duration: float = 0.0
    error_message: Optional[str] = None


@dataclass
class CIResult:
    """Complete CI/test execution result.

    This is the PRIMARY feedback signal. NO synthetic data allowed.
    """

    # Overall status
    status: str  # passed | failed | unknown

    # Test metrics (REAL ONLY)
    test_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0

    # Failed tests
    failed_tests: List[TestResult] = field(default_factory=list)

    # Execution time
    duration: float = 0.0

    # CI checks (from GitHub Actions)
    ci_checks: List[Dict] = field(default_factory=list)

    # Build/lint results (if available)
    build_success: Optional[bool] = None
    lint_errors: int = 0

    # Security scan (if available)
    security_issues: int = 0

    # Unknown markers
    tests_run: bool = True  # False if we couldn't run tests
    ci_available: bool = True  # False if CI data not accessible

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CICollector:
    """Collect real CI and test signals.

    STRICT RULE: All data must be from real execution or marked as unknown.
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def run_local_tests(self, test_command: Optional[str] = None) -> CIResult:
        """Run tests locally and collect results.

        Args:
            test_command: Test command to run (e.g., "pytest", "npm test")
                         If None, will try to detect

        Returns:
            CIResult with real test data
        """
        if test_command is None:
            test_command = self._detect_test_command()

        if not test_command:
            return CIResult(status="unknown", tests_run=False)

        result = CIResult(status="unknown")

        try:
            # Run tests
            proc = subprocess.run(
                test_command.split(),
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            # Parse output based on test framework
            if "pytest" in test_command:
                self._parse_pytest_output(proc.stdout + proc.stderr, result)
            elif "npm test" in test_command or "jest" in test_command:
                self._parse_jest_output(proc.stdout + proc.stderr, result)
            else:
                # Generic parsing
                self._parse_generic_output(proc.stdout + proc.stderr, result)

            # Determine status from return code if not already set
            if result.status == "unknown":
                if proc.returncode == 0:
                    result.status = "passed"
                else:
                    result.status = "failed"

        except subprocess.TimeoutExpired:
            result.status = "failed"
            result.tests_run = False
        except Exception as e:
            result.status = "unknown"
            result.tests_run = False

        # Decision: Test execution complete
        emit_decision(
            decision_type="execution.tests_run",
            context={
                "repo_path": str(self.repo_path),
                "test_command": test_command,
                "tests_run": result.tests_run,
            },
            outcome={
                "status": result.status,
                "test_count": result.test_count,
                "passed": result.passed_count,
                "failed": result.failed_count,
                "duration": result.duration,
            },
            reasoning={
                "rationale": f"Executed {test_command} with {result.passed_count}/{result.test_count} tests passed"
            },
            confidence=1.0 if result.tests_run else 0.5,
            policy_applied="AUTO",
            source_subsystem="execution.ci_collector",
        )

        # Event: For analytics consumption — via spool pipeline (Slice 3)
        _env = CanonicalEventEnvelope(
            event_type=CanonicalEventType.TESTS_EXECUTED.value,
            session_id=None,
            payload={
                "repo_path": redact_file_path(str(self.repo_path)),
                "test_command": redact_bash_command(test_command),
                "status": result.status,
                "test_count": result.test_count,
                "passed": result.passed_count,
                "failed": result.failed_count,
                "duration": result.duration,
                "tests_run": result.tests_run,
            },
            confidence="unavailable",
            project_id=None,
        )
        write_envelopes([_env])

        return result

    def collect_ci_status(self, pr_number: int) -> CIResult:
        """Collect CI status from GitHub Actions.

        Args:
            pr_number: PR number

        Returns:
            CIResult with CI data
        """
        result = CIResult(status="unknown", tests_run=False)

        try:
            proc = subprocess.run(
                ["gh", "pr", "checks", str(pr_number), "--json", "name,status,conclusion"],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
                text=True,
            )

            checks = json.loads(proc.stdout)
            result.ci_checks = checks

            # Determine overall status
            if not checks:
                result.status = "unknown"
                result.ci_available = False
            elif all(c.get("conclusion") == "success" for c in checks):
                result.status = "passed"
            elif any(c.get("conclusion") == "failure" for c in checks):
                result.status = "failed"
            else:
                result.status = "unknown"  # Still running

        except (subprocess.CalledProcessError, json.JSONDecodeError):
            result.ci_available = False

        return result

    def collect_full_feedback(
        self, pr_number: Optional[int] = None, test_command: Optional[str] = None
    ) -> CIResult:
        """Collect all available feedback signals.

        Args:
            pr_number: PR number (if available)
            test_command: Local test command

        Returns:
            CIResult with all real signals
        """
        # Try CI first
        if pr_number:
            result = self.collect_ci_status(pr_number)
            if result.status != "unknown":
                return result

        # Fallback to local tests
        result = self.run_local_tests(test_command)
        return result

    def _detect_test_command(self) -> Optional[str]:
        """Detect test command from repository.

        Returns:
            Test command or None
        """
        # Check for pytest
        if (self.repo_path / "pytest.ini").exists() or (self.repo_path / "setup.py").exists():
            return "pytest"

        # Check for package.json
        package_json = self.repo_path / "package.json"
        if package_json.exists():
            try:
                with open(package_json, "r") as f:
                    data = json.load(f)
                    if "scripts" in data and "test" in data["scripts"]:
                        return "npm test"
            except Exception:
                pass

        return None

    def _parse_pytest_output(self, output: str, result: CIResult):
        """Parse pytest output.

        Args:
            output: Test output
            result: CIResult to populate
        """
        # Look for summary line: "5 passed, 2 failed in 1.23s"
        summary_pattern = r"(\d+)\s+passed"
        failed_pattern = r"(\d+)\s+failed"
        skipped_pattern = r"(\d+)\s+skipped"
        duration_pattern = r"in\s+([\d.]+)s"

        if match := re.search(summary_pattern, output):
            result.passed_count = int(match.group(1))

        if match := re.search(failed_pattern, output):
            result.failed_count = int(match.group(1))

        if match := re.search(skipped_pattern, output):
            result.skipped_count = int(match.group(1))

        if match := re.search(duration_pattern, output):
            result.duration = float(match.group(1))

        result.test_count = result.passed_count + result.failed_count + result.skipped_count

        # Determine status
        if result.failed_count > 0:
            result.status = "failed"
        elif result.test_count > 0:
            result.status = "passed"

        # Parse individual failures
        failure_pattern = r"FAILED\s+([^\s]+)\s+-\s+(.+?)(?=\n|$)"
        for match in re.finditer(failure_pattern, output):
            result.failed_tests.append(
                TestResult(
                    test_name=match.group(1), status="failed", error_message=match.group(2).strip()
                )
            )

    def _parse_jest_output(self, output: str, result: CIResult):
        """Parse Jest output.

        Args:
            output: Test output
            result: CIResult to populate
        """
        # Jest summary: "Tests: 5 passed, 2 failed, 7 total"
        passed_pattern = r"(\d+)\s+passed"
        failed_pattern = r"(\d+)\s+failed"
        total_pattern = r"(\d+)\s+total"

        if match := re.search(passed_pattern, output):
            result.passed_count = int(match.group(1))

        if match := re.search(failed_pattern, output):
            result.failed_count = int(match.group(1))

        if match := re.search(total_pattern, output):
            result.test_count = int(match.group(1))

        # Determine status
        if result.failed_count > 0:
            result.status = "failed"
        elif result.test_count > 0:
            result.status = "passed"

    def _parse_generic_output(self, output: str, result: CIResult):
        """Generic test output parsing.

        Args:
            output: Test output
            result: CIResult to populate
        """
        # Look for common patterns
        if "FAILED" in output or "FAIL" in output or "Error" in output:
            result.status = "failed"
            result.test_count = 1  # At least 1 test ran
        elif "PASSED" in output or "OK" in output or "All tests passed" in output:
            result.status = "passed"
            result.test_count = 1

    def check_build_status(self, build_command: Optional[str] = None) -> bool:
        """Check if code builds successfully.

        Args:
            build_command: Build command (e.g., "npm run build", "python -m py_compile")

        Returns:
            True if build succeeds, False otherwise
        """
        if not build_command:
            # Try to detect
            if (self.repo_path / "package.json").exists():
                build_command = "npm run build"
            else:
                # No build step detected
                return True

        try:
            subprocess.run(
                build_command.split(),
                cwd=self.repo_path,
                capture_output=True,
                check=True,
                timeout=300,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
