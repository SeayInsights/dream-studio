"""A test that builds a repository says so, and skips, when git is not installed.

Before ``tests/helpers/git_repo.py`` checked, a PATH without git ended every such test in
``FileNotFoundError: [WinError 2]`` -- an error that names nothing. These tests run on a machine
that HAS git by hiding it from the helper (``shutil.which``), so they prove the skip without
needing the absence they describe.
"""

from __future__ import annotations

import shutil

import pytest

from tests.helpers import git_repo


@pytest.fixture
def no_git(monkeypatch):
    monkeypatch.setattr(git_repo.shutil, "which", lambda name, *a, **kw: None)


def test_the_helper_skips_with_the_reason_when_git_is_missing(no_git, tmp_path):
    with pytest.raises(pytest.skip.Exception) as raised:
        git_repo.git(tmp_path, "status")
    assert "git is not on PATH" in str(raised.value)
    assert git_repo.NO_GIT_REASON in str(raised.value)


@pytest.mark.parametrize(
    "build",
    [
        lambda path: git_repo.init_repo(path / "r"),
        lambda path: git_repo.commit(path, "m", files={"a.txt": "a"}),
        lambda path: git_repo.tag(path, "v1"),
    ],
    ids=["init_repo", "commit", "tag"],
)
def test_every_way_into_the_helper_skips(no_git, tmp_path, build):
    with pytest.raises(pytest.skip.Exception):
        build(tmp_path)


def test_the_helper_does_not_skip_when_git_is_present(tmp_path):
    if shutil.which("git") is None:
        pytest.skip(git_repo.NO_GIT_REASON)
    repo = git_repo.init_repo(tmp_path / "r")
    assert git_repo.commit(repo, "m", files={"a.txt": "a"})


def test_the_requires_git_marker_skips_exactly_when_git_is_absent():
    mark = git_repo.requires_git.mark
    assert mark.name == "skipif"
    assert mark.kwargs["reason"] == git_repo.NO_GIT_REASON
    assert mark.args == ((shutil.which("git") is None),)
