"""`ds project onboard <path>` gives an external checkout both halves at once.

THE TWO HALVES WERE BUILT AND NEVER JOINED. `ds project register` writes the authority
row and the `.dream-studio-project` marker. `ds integrate install` writes the adapter
surface -- but only into the directory it is run from or the operator's home, because
`detect_claude_code` derives the config root from the working directory and nothing let a
caller name a different one.

So a project could be registered, carry work orders, and have nothing on disk telling an
agent working inside it that Dream Studio exists. Measured: Dream Command had 14 work
orders in the authority and no adapter surface in its checkout.

These drive the real CLI through `parse_args`, not a hand-built namespace -- #751 fixed
exactly that shortcut, and a required flag is invisible to a test that fabricates the
namespace it is supposed to prove.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A Dream Studio home with a bootstrapped authority, never the operator's."""
    ds_home = tmp_path / "dshome"
    (ds_home / "state").mkdir(parents=True, exist_ok=True)
    bootstrap_database(ds_home / "state" / "studio.db")
    return ds_home


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """An external project directory with no adapter surface -- the Dream Command case."""
    d = tmp_path / "some-external-project"
    (d / "src").mkdir(parents=True)
    (d / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    return d


def _run(argv: list[str], home: Path, capsys) -> tuple[int, dict]:
    """Drive the real CLI entry point, then read the JSON it printed.

    `main()` and not a hand-built namespace: #751 fixed exactly that shortcut, and a
    required flag is invisible to a test that fabricates the namespace meant to prove it.
    """
    from interfaces.cli.ds import main

    code = main(["--home", str(home), "--source-root", str(REPO_ROOT), *argv])
    out = capsys.readouterr().out
    start = out.index("{")
    return code, json.loads(out[start:])


# --------------------------------------------------------------------------
# A plan changes nothing -- not the repo, not the authority
# --------------------------------------------------------------------------


def test_a_plan_writes_nothing_at_all(home, checkout, capsys):
    """Registering the project and only pretending about the files would be the worse
    half of a dry run: the part that is hard to undo done, the part you can see not."""
    code, result = _run(
        ["project", "onboard", str(checkout), "--description", "A checkout to onboard.", "--plan"],
        home,
        capsys,
    )
    assert code == 0
    assert result["mode"] == "plan"
    assert result["plan"], "a plan that lists nothing has proved nothing"

    assert not (checkout / ".claude").exists(), "the plan wrote an adapter surface"
    assert not (checkout / ".dream-studio-project").exists(), "the plan wrote a marker"

    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    try:
        count = conn.execute("SELECT COUNT(*) FROM business_projects").fetchone()[0]
    finally:
        conn.close()
    assert count == 0, "the plan registered the project in the authority"


def test_the_plan_targets_the_named_directory_not_the_cwd(home, checkout, capsys):
    """The whole point. `ds integrate install` could only ever write into the directory it
    ran from, which is why a registered project could have no surface."""
    _, result = _run(
        ["project", "onboard", str(checkout), "--description", "A checkout to onboard.", "--plan"],
        home,
        capsys,
    )
    assert Path(result["config_root"]) == checkout / ".claude"
    assert Path.cwd() not in Path(result["config_root"]).parents


# --------------------------------------------------------------------------
# Executing writes both halves
# --------------------------------------------------------------------------


def test_onboarding_writes_the_authority_row_and_the_adapter_surface(home, checkout, capsys):
    code, result = _run(
        ["project", "onboard", str(checkout), "--description", "A checkout to onboard."],
        home,
        capsys,
    )
    assert code == 0, result
    assert result["ok"] is True

    # Half one: the authority knows about it.
    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    try:
        row = conn.execute(
            "SELECT name, project_path FROM business_projects WHERE project_id = ?",
            (result["project_id"],),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "onboarding reported ok and registered nothing"
    assert row[0] == "some-external-project", "the name defaults to the directory's own"
    assert Path(row[1]) == checkout

    # Half two: the checkout knows about Dream Studio.
    assert (checkout / ".claude").is_dir(), "no adapter surface was written"
    assert (checkout / ".claude" / "skills").is_dir()
    assert (checkout / ".dream-studio-project").is_file(), "no attribution marker"


def test_onboarding_twice_does_not_duplicate_the_project(home, checkout, capsys):
    """The projects that need this most already HAVE a row -- they are missing the
    surface. Re-onboarding must repair the second half, not fork the first."""
    _, first = _run(
        ["project", "onboard", str(checkout), "--description", "A checkout to onboard."],
        home,
        capsys,
    )
    _, second = _run(
        ["project", "onboard", str(checkout), "--description", "A checkout to onboard."],
        home,
        capsys,
    )
    assert second["project_id"] == first["project_id"]

    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    try:
        count = conn.execute("SELECT COUNT(*) FROM business_projects").fetchone()[0]
    finally:
        conn.close()
    assert count == 1, "a second onboarding forked the project"


# --------------------------------------------------------------------------
# What it refuses, and what it does not do behind your back
# --------------------------------------------------------------------------


def test_a_path_that_is_not_a_directory_is_refused_before_anything_is_written(
    home, tmp_path, capsys
):
    """A typo would otherwise register a project pointing at nothing, and the CWD resolver
    would attribute none of its work -- a failure that surfaces much later as missing
    telemetry rather than as an error here."""
    code, result = _run(
        ["project", "onboard", str(tmp_path / "nope"), "--description", "Does not exist."],
        home,
        capsys,
    )
    assert code == 1
    assert result["ok"] is False
    assert "Not a directory" in result["error"]

    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    try:
        count = conn.execute("SELECT COUNT(*) FROM business_projects").fetchone()[0]
    finally:
        conn.close()
    assert count == 0


def test_no_git_hook_is_installed_unless_it_is_asked_for(home, checkout, capsys):
    """A hook in somebody else's repository runs on every push they make. That is a thing
    to opt into, not to discover -- so `--git-hook` is off by default and the installer is
    handed no `git_repo_root` without it."""
    (checkout / ".git" / "hooks").mkdir(parents=True)

    _, result = _run(
        ["project", "onboard", str(checkout), "--description", "A checkout to onboard."],
        home,
        capsys,
    )
    assert result["git_hook"] is False
    assert not (
        checkout / ".git" / "hooks" / "pre-push"
    ).exists(), "onboarding installed a git hook nobody asked for"


def test_the_description_is_required_at_this_door(home, checkout):
    """A project is the top of the same prompt chain its milestones, work orders and tasks
    sit in. No length floor, unlike those three -- nine projects is too thin a corpus to
    derive one from, and brownfield intake generates a short description on purpose. But
    an author reaching this door is asked."""
    from interfaces.cli.ds import main

    with pytest.raises(SystemExit):
        main(["--home", str(home), "project", "onboard", str(checkout)])
