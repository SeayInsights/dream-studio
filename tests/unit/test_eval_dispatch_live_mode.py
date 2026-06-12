"""Tests for _eval_dispatch live-mode branch: delta_from_fixture_baseline and failure_reasons (WO 1ce3aad7)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALS_DIR = REPO_ROOT / "tests" / "evals"


def _make_eval_result(*, passed: bool, baseline_score: float = 0.9, composite_score: float = 0.75):
    from core.eval.schema import EvalResult, MatchResult

    return EvalResult(
        eval_id="test-eval",
        version="1.0.0",
        passed=passed,
        composite_score=composite_score,
        event_score=composite_score,
        baseline_score=baseline_score,
        run_mode="live",
        match_result=MatchResult(
            score=composite_score,
            matched_required=0,
            total_required=0,
            negative_violations=["unwanted_event"] if not passed else [],
            missing_events=["expected_event"] if not passed else [],
            out_of_order=[],
        ),
    )


def _make_eval_case_path(tmp_path: Path) -> Path:
    import json as _json

    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()
    case_data = {
        "eval_id": "test-eval",
        "version": "1.0.0",
        "skill_id": "ds-core",
        "description": "test case",
        "input_prompt": "dummy",
        "expected_events": [],
        "forbidden_events": [],
    }
    case_path = evals_dir / "test-eval.json"
    case_path.write_text(_json.dumps(case_data))
    return evals_dir


class TestEvalDispatchLiveMode:
    def test_live_mode_output_includes_delta_from_fixture_baseline(self, tmp_path):
        """--live output contains delta_from_fixture_baseline field."""
        from interfaces.cli.ds import _eval_dispatch

        evals_dir = _make_eval_case_path(tmp_path)
        result = _make_eval_result(passed=False, baseline_score=0.9, composite_score=0.75)

        args = argparse.Namespace(
            eval_command="run",
            eval_id="test-eval",
            evals_dir=str(evals_dir),
            skill_filter=None,
            all=False,
            live=True,
        )
        output = []
        with (
            patch("core.eval.runner.EvalRunner.run_case", return_value=result),
            patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
        ):
            _eval_dispatch(args, source_root=REPO_ROOT)

        assert output, "Expected JSON output"
        data = json.loads(output[0])
        assert "delta_from_fixture_baseline" in data
        assert data["delta_from_fixture_baseline"] == round(0.9 - 0.75, 4)

    def test_live_mode_output_includes_failure_reasons(self, tmp_path):
        """--live output contains failure_reasons combining missing_events and negative_violations."""
        from interfaces.cli.ds import _eval_dispatch

        evals_dir = _make_eval_case_path(tmp_path)
        result = _make_eval_result(passed=False)

        args = argparse.Namespace(
            eval_command="run",
            eval_id="test-eval",
            evals_dir=str(evals_dir),
            skill_filter=None,
            all=False,
            live=True,
        )
        output = []
        with (
            patch("core.eval.runner.EvalRunner.run_case", return_value=result),
            patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
        ):
            _eval_dispatch(args, source_root=REPO_ROOT)

        data = json.loads(output[0])
        assert "failure_reasons" in data
        assert "expected_event" in data["failure_reasons"]
        assert "unwanted_event" in data["failure_reasons"]

    def test_non_live_mode_output_excludes_delta_and_failure_reasons(self, tmp_path):
        """Non-live run does NOT include delta_from_fixture_baseline or failure_reasons."""
        from interfaces.cli.ds import _eval_dispatch

        evals_dir = _make_eval_case_path(tmp_path)
        result = _make_eval_result(passed=False, baseline_score=0.9, composite_score=0.75)
        # Override run_mode to simulate fixture run
        result.run_mode = "fixture"

        args = argparse.Namespace(
            eval_command="run",
            eval_id="test-eval",
            evals_dir=str(evals_dir),
            skill_filter=None,
            all=False,
            live=False,
        )
        output = []
        with (
            patch("core.eval.runner.EvalRunner.run_case", return_value=result),
            patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
        ):
            _eval_dispatch(args, source_root=REPO_ROOT)

        data = json.loads(output[0])
        assert "delta_from_fixture_baseline" not in data
        assert "failure_reasons" not in data

    def test_live_mode_passing_run_has_empty_failure_reasons(self, tmp_path):
        """--live passing run: failure_reasons is empty list, delta is baseline - 1.0."""
        from interfaces.cli.ds import _eval_dispatch

        evals_dir = _make_eval_case_path(tmp_path)
        result = _make_eval_result(passed=True, baseline_score=0.9, composite_score=1.0)

        args = argparse.Namespace(
            eval_command="run",
            eval_id="test-eval",
            evals_dir=str(evals_dir),
            skill_filter=None,
            all=False,
            live=True,
        )
        output = []
        with (
            patch("core.eval.runner.EvalRunner.run_case", return_value=result),
            patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
        ):
            _eval_dispatch(args, source_root=REPO_ROOT)

        data = json.loads(output[0])
        assert data["failure_reasons"] == []
        assert data["delta_from_fixture_baseline"] == round(0.9 - 1.0, 4)
