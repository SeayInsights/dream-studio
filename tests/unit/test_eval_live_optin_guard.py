"""WO-EVAL-LIVE-GATE (d176fb5c): lock the eval runner's --live escape hatch as opt-in.

`--live` spawns a real `claude` subprocess to *generate* events (scored by the same
deterministic matcher). It is an intentional developer-only escape hatch — but it must
never silently become the default or run in CI. These guards assert the boundary:
the default path is fixture-only and never shells out; live=True is required to reach
the subprocess; the flags default to False.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.eval.runner import EvalRunner
from core.eval.schema import EvalCase, EvalResult, MatchResult


def _case() -> EvalCase:
    # fixture_events=[] (not None) keeps run_case on the deterministic fixture path.
    return EvalCase(
        eval_id="guard-eval",
        version="1.0.0",
        description="opt-in guard",
        skill_id="ds-core",
        input_prompt="dummy",
        fixture_events=[],
    )


def _fake_live_result() -> EvalResult:
    return EvalResult(
        eval_id="guard-eval",
        version="1.0.0",
        passed=True,
        composite_score=1.0,
        event_score=1.0,
        match_result=MatchResult(
            score=1.0,
            matched_required=0,
            total_required=0,
            negative_violations=[],
            missing_events=[],
            out_of_order=[],
        ),
        run_mode="live",
    )


def test_default_run_case_never_shells_out(tmp_path: Path) -> None:
    runner = EvalRunner(db_path=tmp_path / "eval.db")
    with (
        patch("core.eval.runner.subprocess.run") as proc,
        patch("core.eval.runner.shutil.which") as which,
    ):
        runner.run_case(_case())  # default: no live flag
        proc.assert_not_called()
        which.assert_not_called()


def test_default_run_case_does_not_reach_live(tmp_path: Path) -> None:
    runner = EvalRunner(db_path=tmp_path / "eval.db")
    with patch.object(EvalRunner, "_run_case_live", MagicMock()) as live:
        runner.run_case(_case())
        live.assert_not_called()


def test_live_true_routes_to_live(tmp_path: Path) -> None:
    runner = EvalRunner(db_path=tmp_path / "eval.db")
    with patch.object(
        EvalRunner, "_run_case_live", MagicMock(return_value=_fake_live_result())
    ) as live:
        runner.run_case(_case(), live=True)
        live.assert_called_once()


def test_run_case_and_run_all_default_live_false() -> None:
    for method in ("run_case", "run_all"):
        sig = inspect.signature(getattr(EvalRunner, method))
        assert sig.parameters["live"].default is False, f"{method}.live must default to False"


def test_cli_live_flag_defaults_to_false() -> None:
    import argparse

    from interfaces.cli.commands.eval import register

    parser = argparse.ArgumentParser()
    register(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["eval", "run", "--eval-id", "x"])
    assert args.live is False
