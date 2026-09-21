"""The branch-freshness detector the lane declared and nobody wrote.

`a-branch-behind-its-base` named `py -m core.gates.branch_freshness` as its
enforcement. The module did not exist, so the lane read as mechanically checked
while nothing checked it -- and the registry gate that refuses exactly this was
never wired into pre-push, so the claim stood.

The property that matters most here is the one in `test_cannot_say_is_not_clean`:
a detector that reports a tree it could not read as fresh is worse than no
detector, because it answers the question falsely instead of leaving it open.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.gates import branch_freshness


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(root),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.fixture
def repo(tmp_path):
    """A real repository with a base branch and a working branch off it."""
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    (root / "f.txt").write_text("one\n", encoding="utf-8")
    _git(root, "add", "f.txt")
    _git(root, "commit", "-q", "-m", "one")
    return root


def test_current_branch_reports_current(repo):
    result = branch_freshness.run(repo, base_ref="main")
    assert result["status"] == "current"
    assert result["behind"] == 0


def test_behind_branch_reports_the_distance(repo):
    """The count is the point. 'Behind' without a number does not tell a reviewer
    whether they are reading a materially different tree -- the precedent had
    branches 5 and 38 commits behind, and both mattered."""
    _git(repo, "checkout", "-q", "-b", "work")
    _git(repo, "checkout", "-q", "main")
    for n in ("two", "three"):
        (repo / "f.txt").write_text(f"{n}\n", encoding="utf-8")
        _git(repo, "commit", "-q", "-am", n)
    _git(repo, "checkout", "-q", "work")

    result = branch_freshness.run(repo, base_ref="main")
    assert result["status"] == "behind"
    assert result["behind"] == 2
    assert result["branch"] == "work"


def test_ahead_alone_is_not_behind(repo):
    """A branch with its own commits, fully current with base, is not stale.
    Counting the wrong direction would report every active branch as behind."""
    _git(repo, "checkout", "-q", "-b", "work")
    (repo / "g.txt").write_text("mine\n", encoding="utf-8")
    _git(repo, "add", "g.txt")
    _git(repo, "commit", "-q", "-m", "mine")

    result = branch_freshness.run(repo, base_ref="main")
    assert result["status"] == "current"
    assert result["behind"] == 0
    assert result["ahead"] == 1


def test_cannot_say_is_not_clean(tmp_path):
    """A tree that is not a repository reports unknown, never current.

    This is the load-bearing case. Answering 'current' for a tree it could not
    read would be the compared-nothing-reported-clean shape every review lane
    exists to refuse, and it would be indistinguishable from a real pass.
    """
    result = branch_freshness.run(tmp_path / "not-a-repo")
    assert result["status"] == "unknown"
    assert result["status"] != "current"
    assert "reason" in result


def test_unknown_base_is_unknown_not_current(repo):
    """A base ref that does not exist cannot be measured against. Reporting the
    branch as current would silently pass every branch whenever a fetch failed."""
    result = branch_freshness.run(repo, base_ref="origin/does-not-exist")
    assert result["status"] == "unknown"


def test_unknown_exits_zero_but_says_so(tmp_path, capsys):
    """Exit 0 so a missing git does not manufacture a defect, but the output must
    not read as a pass -- an operator scanning for OK should not find one."""
    rc = branch_freshness.main(["--repo-root", str(tmp_path / "nope")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "UNKNOWN" in out
    assert "OK" not in out


def test_accepts_repo_root(repo):
    """The convener appends --repo-root when pointed at another project. A detector
    that rejects it gets its result reported as that project's finding, which is a
    defect in the lane reported as a defect in the tree."""
    rc = branch_freshness.main(["--repo-root", str(repo), "--base", "main"])
    assert rc == 0
