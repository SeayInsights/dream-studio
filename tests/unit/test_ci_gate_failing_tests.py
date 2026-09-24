"""Tests for ci_gate.py failing_tests field in JSON verdict (WO f0e8f2c0)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest


class TestCiGateFailingTests:
    def test_failing_run_includes_failing_tests_list(self, tmp_path):
        """When test check fails, JSON verdict has non-empty failing_tests list."""
        from interfaces.cli.ci_gate import run_check

        pytest_output = (
            "FAILED tests/unit/test_foo.py::test_bar - AssertionError\n"
            "FAILED tests/unit/test_foo.py::test_baz - TypeError\n"
            "2 failed in 0.5s"
        )
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = pytest_output
        mock_result.stderr = ""

        with patch("interfaces.cli.ci_gate.subprocess.run", return_value=mock_result):
            record = run_check("test", ["py", "-m", "pytest"])

        assert record["passed"] is False
        assert "failing_tests" in record
        assert len(record["failing_tests"]) == 2
        assert "tests/unit/test_foo.py::test_bar" in record["failing_tests"]
        assert "tests/unit/test_foo.py::test_baz" in record["failing_tests"]

    def test_passing_run_has_empty_failing_tests_list(self, tmp_path):
        """When test check passes, failing_tests is an empty list."""
        from interfaces.cli.ci_gate import run_check

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "42 passed in 1.2s"
        mock_result.stderr = ""

        with patch("interfaces.cli.ci_gate.subprocess.run", return_value=mock_result):
            record = run_check("test", ["py", "-m", "pytest"])

        assert record["passed"] is True
        assert "failing_tests" in record
        assert record["failing_tests"] == []

    def test_non_test_check_has_no_failing_tests_field(self, tmp_path):
        """Non-test checks (format, lint) do not include a failing_tests field."""
        from interfaces.cli.ci_gate import run_check

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "would reformat foo.py"
        mock_result.stderr = ""

        with patch("interfaces.cli.ci_gate.subprocess.run", return_value=mock_result):
            record = run_check("format", ["py", "-m", "black", "--check", "."])

        assert "failing_tests" not in record

    def test_isolated_check_env_neutralizes_ambient_changed_files(self, monkeypatch):
        """contract-docs-drift runs through this same isolated env (every non-test
        check does). pre-push.yaml's manifest pins DREAM_STUDIO_CHANGED_FILES to ""
        for exactly this reason -- the gate honors it as a real, documented
        override that bypasses git-based diffing entirely -- but this entry point
        builds its own env by copying os.environ, with no pin at all: an ambient
        value exported in whatever shell invokes ci_gate.py directly would leak
        through here even though pre-push.yaml is already patched against it."""
        from interfaces.cli.ci_gate import run_check

        monkeypatch.setenv(
            "DREAM_STUDIO_CHANGED_FILES", "core/shared_intelligence/contract_atlas.py"
        )
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("interfaces.cli.ci_gate.subprocess.run", return_value=mock_result) as mock_run:
            run_check("contract-docs-drift", ["py", "interfaces/cli/contract_docs_drift_gate.py"])

        passed_env = mock_run.call_args.kwargs["env"]
        assert passed_env.get("DREAM_STUDIO_CHANGED_FILES") == "", (
            "an ambient DREAM_STUDIO_CHANGED_FILES leaked into the isolated check env "
            f"unpinned: {passed_env.get('DREAM_STUDIO_CHANGED_FILES')!r}"
        )

    def test_extract_failing_tests_parses_pytest_format(self):
        """_extract_failing_tests returns node IDs from pytest FAILED lines."""
        from interfaces.cli.ci_gate import _extract_failing_tests

        output = (
            "FAILED tests/unit/test_a.py::test_one - AssertionError: expected 1 got 2\n"
            "FAILED tests/evals/test_b.py::TestClass::test_two\n"
            "1 warning\n"
            "2 failed in 0.3s"
        )
        result = _extract_failing_tests(output)
        assert result == [
            "tests/unit/test_a.py::test_one",
            "tests/evals/test_b.py::TestClass::test_two",
        ]
