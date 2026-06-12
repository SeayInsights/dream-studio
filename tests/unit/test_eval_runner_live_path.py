"""Tests for EvalRunner.run_case(live=True) and run_all(live=True) paths (WO 63f09915)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]

_CASE_JSON = {
    "eval_id": "eval-live-test",
    "version": "1.0.0",
    "skill_id": "ds-core",
    "description": "test",
    "input_prompt": "dummy prompt",
    "expected_events": [],
    "fixture_events": [],
}


def _make_eval_case():
    from core.eval.schema import EvalCase

    return EvalCase(
        eval_id="eval-live-test",
        version="1.0.0",
        skill_id="ds-core",
        description="test",
        input_prompt="dummy prompt",
        expected_events=[],
        fixture_events=[],
    )


def _make_live_result(eval_id: str = "eval-live-test"):
    from core.eval.schema import EvalResult, MatchResult

    return EvalResult(
        eval_id=eval_id,
        version="1.0.0",
        passed=True,
        composite_score=1.0,
        event_score=1.0,
        run_mode="live",
        baseline_score=0.9,
        match_result=MatchResult(
            score=1.0,
            matched_required=0,
            total_required=0,
            negative_violations=[],
            missing_events=[],
            out_of_order=[],
        ),
    )


class TestRunCaseLivePath:
    def test_run_case_live_true_routes_to_run_case_live(self, tmp_path):
        """run_case(live=True) delegates to _run_case_live and returns its result."""
        from core.eval.runner import EvalRunner

        runner = EvalRunner(evals_dir=tmp_path)
        case = _make_eval_case()
        expected = _make_live_result()

        with patch.object(runner, "_run_case_live", return_value=expected) as mock_live:
            result = runner.run_case(case, live=True)

        mock_live.assert_called_once_with(case)
        assert result.run_mode == "live"

    def test_run_case_live_false_does_not_call_run_case_live(self, tmp_path):
        """run_case(live=False) does NOT call _run_case_live."""
        from core.eval.runner import EvalRunner

        runner = EvalRunner(evals_dir=tmp_path)
        case = _make_eval_case()

        with (
            patch.object(runner, "_run_case_live") as mock_live,
            patch("core.eval.runner.match_events") as mock_match,
            patch("core.eval.runner.save_run_result", return_value=(True, False)),
            patch("core.eval.runner.load_baseline", return_value=None),
        ):
            mock_match.return_value = MagicMock(
                score=1.0, missing_events=[], negative_violations=[], out_of_order=[]
            )
            runner.run_case(case, live=False)

        mock_live.assert_not_called()


class TestRunAllLiveParameter:
    def test_run_all_live_true_passes_live_to_each_run_case(self, tmp_path):
        """run_all(live=True) calls run_case with live=True for each case."""
        from core.eval.runner import EvalRunner

        evals_dir = tmp_path / "evals"
        evals_dir.mkdir()
        (evals_dir / "eval_live_test.json").write_text(json.dumps(_CASE_JSON))

        runner = EvalRunner(evals_dir=evals_dir)
        live_result = _make_live_result()

        with patch.object(runner, "run_case", return_value=live_result) as mock_run:
            runner.run_all(live=True)

        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs.get("live") is True, "run_all(live=True) must pass live=True to run_case"

    def test_run_all_live_false_passes_live_false(self, tmp_path):
        """run_all() default calls run_case with live=False."""
        from core.eval.runner import EvalRunner

        evals_dir = tmp_path / "evals"
        evals_dir.mkdir()
        (evals_dir / "eval_live_test.json").write_text(json.dumps(_CASE_JSON))

        runner = EvalRunner(evals_dir=evals_dir)
        fixture_result = _make_live_result()
        fixture_result.run_mode = "fixture"

        with patch.object(runner, "run_case", return_value=fixture_result) as mock_run:
            runner.run_all()

        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs.get("live") is False


class TestEvalRunCliLiveFlag:
    def test_cli_live_flag_wires_live_true_to_runner(self, tmp_path):
        """ds eval run <id> --live passes live=True to EvalRunner.run_case."""
        from interfaces.cli.ds import _eval_dispatch

        evals_dir = tmp_path / "evals"
        evals_dir.mkdir()
        case_data = dict(_CASE_JSON, eval_id="wire-test")
        (evals_dir / "wire-test.json").write_text(json.dumps(case_data))

        live_result = _make_live_result("wire-test")

        args = argparse.Namespace(
            eval_command="run",
            eval_id="wire-test",
            evals_dir=str(evals_dir),
            skill_filter=None,
            all=False,
            live=True,
        )

        with (
            patch("core.eval.runner.EvalRunner.run_case", return_value=live_result) as mock_run,
            patch("builtins.print"),
        ):
            _eval_dispatch(args, source_root=REPO_ROOT)

        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs.get("live") is True, "--live flag must wire live=True to run_case"
