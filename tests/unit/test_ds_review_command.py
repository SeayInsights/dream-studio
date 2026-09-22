"""`ds review` — the door, and the one substitution it must refuse.

The round table has carried `--repo-root`, `--seat`, `--lane`, `--all` and `--json` for a
while, reachable only as `py -m core.gates.round_table`. A capability the CLI does not
expose is one every caller has to name an internal module for. These pin that the door
exists and that `--pr` means what it says.
"""

from __future__ import annotations

import argparse
import subprocess
from unittest import mock

import pytest

from interfaces.cli.commands import review as review_cmd


def _args(**overrides) -> argparse.Namespace:
    base = {
        "repo": None,
        "pr": None,
        "seat": None,
        "lane_id": None,
        "all_seats": False,
        "no_detectors": True,
        "json": True,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


# ── the door exists ─────────────────────────────────────────────────────────


def test_ds_exposes_review():
    """The whole point of D17: reachable as `ds review`, not only as a module path."""
    from interfaces.cli import ds

    parser = ds.build_parser() if hasattr(ds, "build_parser") else None
    if parser is None:
        # Fall back to the source: the three wiring points must all be present, because
        # an import without a register() is a command that exists and cannot be reached.
        import pathlib

        source = pathlib.Path(ds.__file__).read_text(encoding="utf-8")
        assert "import review as review_cmd" in source
        assert "review_cmd.register(subcommands)" in source
        assert 'args.command == "review"' in source
        return
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    assert "review" in action.choices


def test_the_review_parser_carries_repo_and_pr():
    """D17 names both flags; a door missing one is the module path with extra steps."""
    sub = argparse.ArgumentParser().add_subparsers()
    review_cmd.register(sub)
    flags = {
        option for action in sub.choices["review"]._actions for option in action.option_strings
    }
    assert {"--repo", "--pr", "--seat", "--lane", "--all", "--json"} <= flags


# ── --pr must not degrade into a review of something else ───────────────────


def _completed(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_pr_paths_are_the_prs_files():
    with mock.patch.object(
        review_cmd.subprocess, "run", return_value=_completed(0, "a/b.py\nc/d.md\n")
    ):
        assert review_cmd.pr_changed_paths("812") == ["a/b.py", "c/d.md"]


def test_a_pr_that_cannot_be_read_raises_rather_than_returning_empty():
    """An empty list is how `changed_paths` says "I could not tell", and its caller reads
    that as a reason to convene EVERYTHING. Correct there; a misreport here."""
    with mock.patch.object(
        review_cmd.subprocess, "run", return_value=_completed(1, stderr="no pull requests found")
    ):
        with pytest.raises(RuntimeError, match="no pull requests found"):
            review_cmd.pr_changed_paths("99999")


def test_missing_gh_is_named_not_swallowed():
    with mock.patch.object(review_cmd.subprocess, "run", side_effect=FileNotFoundError()):
        with pytest.raises(RuntimeError, match="not on PATH"):
            review_cmd.pr_changed_paths("812")


def test_a_pr_with_no_files_refuses():
    """Zero files would become `paths=[]`, which convene() reads as "review everything"."""
    with mock.patch.object(review_cmd.subprocess, "run", return_value=_completed(0, "\n")):
        with pytest.raises(RuntimeError, match="no changed files"):
            review_cmd.pr_changed_paths("812")


def test_dispatch_refuses_instead_of_convening_when_the_pr_cannot_be_read(capsys):
    """THE MUTANT THIS EXISTS FOR. A `--pr` that fell back to the local change set would
    print a full, plausible report that the operator reads as being about the PR. The
    failure has to reach the exit code, and convene must never be called."""
    with mock.patch.object(review_cmd, "pr_changed_paths", side_effect=RuntimeError("boom")):
        with mock.patch("core.gates.round_table.convene") as convened:
            rc = review_cmd.dispatch(_args(pr="812"), source_root=None, dream_studio_home=None)
    assert rc == 2
    assert not convened.called, "convened anyway -- the report would misname its subject"
    assert "boom" in capsys.readouterr().err


def test_dispatch_hands_the_prs_paths_to_convene():
    """The wiring, not the pieces: nothing above proves dispatch passes `paths` through."""
    with mock.patch.object(review_cmd, "pr_changed_paths", return_value=["x/y.py"]):
        with mock.patch(
            "core.gates.round_table.convene", return_value={"status": "pass", "lanes": []}
        ) as convened:
            rc = review_cmd.dispatch(_args(pr="812"), source_root=None, dream_studio_home=None)
    assert rc == 0
    assert convened.call_args.kwargs["paths"] == ["x/y.py"]


def test_without_pr_convene_chooses_its_own_change_set():
    """`paths=None` is what lets convene fall back to git -- passing [] would mean
    "review everything" and passing the local diff would duplicate its logic."""
    with mock.patch(
        "core.gates.round_table.convene", return_value={"status": "pass", "lanes": []}
    ) as convened:
        review_cmd.dispatch(_args(), source_root=None, dream_studio_home=None)
    assert convened.call_args.kwargs["paths"] is None


def test_an_unknown_seat_exits_two_rather_than_reporting_clean():
    with mock.patch("core.gates.round_table.convene", side_effect=KeyError("no such seat")):
        rc = review_cmd.dispatch(
            _args(seat="Nonexistent"), source_root=None, dream_studio_home=None
        )
    assert rc == 2


def test_a_failing_report_exits_one():
    with mock.patch("core.gates.round_table.convene", return_value={"status": "fail", "lanes": []}):
        rc = review_cmd.dispatch(_args(), source_root=None, dream_studio_home=None)
    assert rc == 1
