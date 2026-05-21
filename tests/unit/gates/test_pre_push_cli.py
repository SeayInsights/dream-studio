"""B.3 — `ds workflow run pre-push --non-interactive` dispatch tests.

Covers the special-case wiring in `interfaces/cli/ds_workflow.py::cmd_run` that
routes the pre-push command to `core.gates.pre_push` instead of the model-driven
workflow runner.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from interfaces.cli import ds_workflow


def _make_args(wf_key: str, *, non_interactive: bool = False, dry_run: bool = False):
    return argparse.Namespace(
        wf_key=wf_key,
        non_interactive=non_interactive,
        dry_run=dry_run,
    )


def test_non_interactive_pre_push_dispatches_to_gate_runner():
    """`ds workflow run pre-push --non-interactive` calls core.gates.pre_push."""
    from core.gates.pre_push import PrePushReport

    fake_report = PrePushReport(overall_passed=True, gates=[])
    with patch("core.gates.pre_push.run_pre_push_gates", return_value=fake_report) as mock_run:
        exit_code = ds_workflow.cmd_run(_make_args("pre-push", non_interactive=True))
    assert exit_code == 0
    mock_run.assert_called_once()


def test_non_interactive_pre_push_returns_1_on_failure():
    from core.gates.pre_push import PrePushReport

    fake_report = PrePushReport(overall_passed=False, gates=[])
    with patch("core.gates.pre_push.run_pre_push_gates", return_value=fake_report):
        exit_code = ds_workflow.cmd_run(_make_args("pre-push", non_interactive=True))
    assert exit_code == 1


def test_non_interactive_rejects_non_pre_push(capsys):
    """Only `pre-push` is allowed with --non-interactive; other names error out."""
    exit_code = ds_workflow.cmd_run(_make_args("self-audit", non_interactive=True))
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "--non-interactive" in err
    assert "pre-push" in err


def test_interactive_pre_push_does_not_call_gate_runner():
    """Without --non-interactive, pre-push goes through the normal workflow runner path."""
    with patch("core.gates.pre_push.run_pre_push_gates") as mock_gate:
        with patch("control.execution.workflow.runner.WorkflowRunner") as mock_runner_cls:
            mock_runner_cls.return_value.run.return_value = "completed"
            ds_workflow.cmd_run(_make_args("pre-push", non_interactive=False))
    mock_gate.assert_not_called()
    mock_runner_cls.assert_called_once()


def test_parser_accepts_non_interactive_flag():
    """The argument parser exposes --non-interactive on the run subcommand."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    ds_workflow.add_workflow_subcommand(sub)

    args = parser.parse_args(["workflow", "run", "pre-push", "--non-interactive"])
    assert args.non_interactive is True
    assert args.wf_key == "pre-push"
