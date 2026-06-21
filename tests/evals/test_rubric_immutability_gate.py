"""Gate tests: rubric_immutability_gate main() entry point (WO 7dc2f344).

Proving gate:
  no-rubric-change: returns 0, commit messages never fetched
  rubric-with-token: returns 0 and records allow decision
  rubric-without-token: returns 1 and records block decision
  no-change-skips-record: _record_decision never called when rubric not in diff
"""

from __future__ import annotations

from unittest.mock import patch


def test_no_rubric_change_returns_zero():
    """Rubric not in diff → exit 0, _commit_messages never called."""
    from core.gates.rubric_immutability_gate import main

    with patch(
        "core.gates.rubric_immutability_gate._changed_files",
        return_value=["src/other.py"],
    ), patch("core.gates.rubric_immutability_gate._commit_messages") as mock_commits:
        rc = main()

    assert rc == 0
    mock_commits.assert_not_called()


def test_rubric_change_with_token_returns_zero():
    """Rubric in diff with [rubric-update] token → exit 0, allow recorded."""
    from core.gates.rubric_immutability_gate import RUBRIC_PATH, main

    with patch(
        "core.gates.rubric_immutability_gate._changed_files",
        return_value=[RUBRIC_PATH],
    ):
        with patch(
            "core.gates.rubric_immutability_gate._commit_messages",
            return_value="fix: update rubric [rubric-update] token present",
        ):
            with patch("core.gates.rubric_immutability_gate._record_decision") as mock_record:
                rc = main()

    assert rc == 0
    mock_record.assert_called_once_with("allow")


def test_rubric_change_without_token_returns_one():
    """Rubric in diff without token → exit 1, block recorded."""
    from core.gates.rubric_immutability_gate import RUBRIC_PATH, main

    with patch(
        "core.gates.rubric_immutability_gate._changed_files",
        return_value=[RUBRIC_PATH],
    ):
        with patch(
            "core.gates.rubric_immutability_gate._commit_messages",
            return_value="fix: some change without the token",
        ):
            with patch("core.gates.rubric_immutability_gate._record_decision") as mock_record:
                rc = main()

    assert rc == 1
    mock_record.assert_called_once_with("block")


def test_no_rubric_change_skips_record_decision():
    """Rubric not in diff → _record_decision never called."""
    from core.gates.rubric_immutability_gate import main

    with patch("core.gates.rubric_immutability_gate._changed_files", return_value=[]):
        with patch("core.gates.rubric_immutability_gate._record_decision") as mock_record:
            rc = main()

    assert rc == 0
    mock_record.assert_not_called()
