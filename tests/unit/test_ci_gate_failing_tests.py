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
