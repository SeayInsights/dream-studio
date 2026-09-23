"""`ds work-order close` prints the main-CI advisory, rather than leaving it in the JSON.

WHY THIS REPLACES A SKILL-TEXT CHECK. `close_work_order` has returned `main_ci_warning`
since WO 55d02acf, and the only thing that surfaced it was a line in the ds-workorder
close mode's SKILL.md instructing the model to print it verbatim. That file was checked by
tests/unit/test_close_skill_ci_guidance.py -- the two-layer rule, which says an engine key
with no reader is a gate an agent cannot act on.

The pack was dissolved and the guarantee moved DOWN rather than sideways: the command
prints the advisory to stderr, beside the bypassed-gate warnings, so it reaches an
operator whether or not any prose is read or any payload is parsed. That is a stronger
arrangement than the one it replaces, and this file is what holds it up.

It stays advisory. A red `main` someone else caused must not block this close, so the
exit code is unchanged -- which is the half a check has to pin, because "advisory" is
exactly the property that erodes when someone later decides a warning should be a failure.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from interfaces.cli.commands.work_order_lifecycle import _work_order_close


def _close(tmp_path, capsys, result: dict):
    with (
        patch("core.work_orders.close.close_work_order", return_value=result),
        patch.object(type(tmp_path), "is_dir", lambda self: True),
    ):
        rc = _work_order_close(
            work_order_id="wo-1",
            force=False,
            skip_verify=True,
            source_root=tmp_path,
            dream_studio_home=tmp_path,
            planning_root=None,
        )
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


OK_WITH_WARNING = {
    "ok": True,
    "work_order_id": "wo-1",
    "main_ci": {"status": "failure", "sha": "abc1234"},
    "main_ci_warning": "main is RED at abc1234 (Full CI failed)",
}


def test_the_advisory_reaches_stderr_not_only_the_payload(tmp_path, capsys):
    rc, out, err = _close(tmp_path, capsys, OK_WITH_WARNING)
    assert rc == 0
    assert "main is RED at abc1234" in err, "the advisory never reached the operator"
    # And it is still in the payload, so a parser is not worse off than a reader.
    assert json.loads(out)["main_ci_warning"] == OK_WITH_WARNING["main_ci_warning"]


def test_the_advisory_does_not_change_the_exit_code(tmp_path, capsys):
    """Advisory is the whole contract. A red main someone else caused must not block
    this close; one you caused is the next thing you work on, not a reason this fails."""
    rc, _out, err = _close(tmp_path, capsys, OK_WITH_WARNING)
    assert rc == 0, "a main-CI warning turned an advisory into a failure"
    assert err.strip(), "the warning was swallowed instead of printed"


def test_a_green_main_prints_nothing(tmp_path, capsys):
    """No warning key, no line. A close that narrated main's health on every run would
    train an operator to skim past the one time it said something."""
    rc, _out, err = _close(
        tmp_path, capsys, {"ok": True, "work_order_id": "wo-1", "main_ci": {"status": "success"}}
    )
    assert rc == 0
    assert "[main-ci]" not in err


@pytest.mark.parametrize("warning", ["", None])
def test_an_empty_warning_is_not_printed_as_an_empty_line(tmp_path, capsys, warning):
    """`unknown` CI state yields a falsy warning, not a blank one. Printing "[main-ci] "
    with nothing after it would read as a truncated message rather than as no news."""
    rc, _out, err = _close(
        tmp_path, capsys, {"ok": True, "work_order_id": "wo-1", "main_ci_warning": warning}
    )
    assert rc == 0
    assert "[main-ci]" not in err
