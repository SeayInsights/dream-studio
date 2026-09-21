"""The test suite must not be able to reach the operator's git repository.

WO 77cb21cc. Symptom, measured over one session: ``core.bare`` on the real repository flipped
to ``true`` six times, the checked-out branch's ref moved on its own, and the repository
collected three commits named ``commit a`` / ``commit b`` / ``commit c`` that nobody authored.
Every flip followed a pre-push gate run. Running the suspected test file by hand never
reproduced it -- which is why it survived so long.

The mechanism: git exports ``GIT_DIR``, pointing at the real repository, to every hook it
runs. The pre-push gate runs pytest, pytest's children inherit ``GIT_DIR``, and a fixture that
calls ``subprocess.run(["git", "init"], cwd=<tmp>)`` then re-initializes THAT repository rather
than the temporary one -- as bare, because the cwd is not its work tree. The commits that
follow land in the real repository too. ``tests/unit/test_graded_range_includes_own_commits.py``
is the fixture that did it; 57 other git subprocess calls across 18 files are shaped the same
way and were one ``git init`` away from the same outcome.

The fix is in ``tests/conftest.py``, beside the guard that stops tests writing the operator's
real database -- the same class of escape, so the same place. It strips the pointers at
conftest import time, which makes the under-a-hook environment identical to the ordinary
``pytest`` one. Fixing the 57 call sites individually would have left the next author free to
write the same three lines.

These tests prove the escape is closed at both layers: the one file that caused the damage
defends itself, and the conftest defends every file including ones not yet written.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The variables git exports to hooks that point a git invocation away from its cwd.
#: GIT_DIR alone caused the damage; the rest are here because a partial strip is the kind of
#: fix that looks done and is not.
REPO_POINTERS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CEILING_DIRECTORIES",
)


def _clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in REPO_POINTERS}
    env.update(extra)
    return env


def _run(repo: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env if env is not None else _clean_env(),
        check=False,
    )


def _victim(tmp_path: Path) -> Path:
    """A repository standing in for the operator's, built with no pointers inherited."""
    victim = tmp_path / "victim"
    victim.mkdir()
    for args in (
        ("init", "-q"),
        ("config", "user.email", "t@example.com"),
        ("config", "user.name", "T"),
    ):
        assert _run(victim, *args).returncode == 0, args
    (victim / "kept.txt").write_text("kept", encoding="utf-8")
    assert _run(victim, "add", ".").returncode == 0
    assert _run(victim, "commit", "-q", "-m", "the victim's own commit").returncode == 0
    return victim


def _bare(repo: Path) -> str:
    return _run(repo, "config", "--get", "core.bare").stdout.strip()


def _log(repo: Path) -> str:
    return _run(repo, "log", "--format=%H").stdout


def test_the_fixture_that_did_it_now_ignores_git_dir(tmp_path, monkeypatch):
    """The symptom test, aimed at a victim instead of the operator's repository.

    This is the file-level defense: even with ``GIT_DIR`` set in the environment, ``_git``
    must operate on its ``cwd`` alone.
    """
    from tests.unit.test_graded_range_includes_own_commits import _git

    victim = _victim(tmp_path)
    assert _bare(victim) in ("false", ""), "the victim started out non-bare"
    before = _log(victim)

    # Exactly what git hands a hook, and through the hook, pytest.
    monkeypatch.setenv("GIT_DIR", str(victim / ".git"))

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    # An escaped `git init` turns the victim bare, and the `git add` after it then dies with
    # "this operation must be run in a work tree". Catching that keeps the failure readable:
    # the assertions below name what was damaged, instead of a CalledProcessError two frames
    # deep in subprocess.
    escaped: Exception | None = None
    try:
        _git(workspace, "init", "-q")
        _git(workspace, "config", "user.email", "t@example.com")
        _git(workspace, "config", "user.name", "T")
        (workspace / "a.txt").write_text("a", encoding="utf-8")
        _git(workspace, "add", ".")
        _git(workspace, "commit", "-q", "-m", "commit a")
    except subprocess.CalledProcessError as exc:  # pragma: no cover - only on a regression
        escaped = exc

    assert _bare(victim) in ("false", ""), (
        "GIT_DIR was honoured: the victim repository was re-initialized as bare. "
        "_git must pass env= with the repository pointers stripped."
    )
    assert _log(victim) == before, "commits landed in the victim repository"
    assert escaped is None, f"the fixture's git calls failed: {escaped}"
    assert (workspace / ".git").exists(), "the work should land in the temporary repository"


def test_importing_conftest_clears_every_inherited_repo_pointer():
    """The conftest strip, exercised with the pointers actually set.

    Asserting on ``os.environ`` from inside this test would be vacuous: an ordinary ``pytest``
    run has no pointers set to begin with, so the assertion would pass against a conftest that
    strips nothing. The import has to happen in a process where they ARE set, which is what
    the subprocess is for.
    """
    fake = {name: str(REPO_ROOT / ".git") for name in REPO_POINTERS}
    probe = (
        "import importlib.util, json, os, sys;"
        "spec = importlib.util.spec_from_file_location('ds_conftest_probe', r'"
        + str(REPO_ROOT / "tests" / "conftest.py")
        + "');"
        "mod = importlib.util.module_from_spec(spec);"
        "sys.modules['ds_conftest_probe'] = mod;"
        "spec.loader.exec_module(mod);"
        "print(json.dumps([n for n in " + repr(list(REPO_POINTERS)) + " if n in os.environ]))"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_clean_env(**fake),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, f"the probe failed to import conftest\n{done.stderr[-2000:]}"
    survivors = json.loads(done.stdout.strip().splitlines()[-1])
    assert not survivors, f"conftest left these repository pointers set: {survivors}"


def test_pytest_under_a_hooks_environment_leaves_the_real_repository_alone(tmp_path):
    """The end-to-end proof, and the only one that reproduces the original conditions.

    A real pytest process, with ``GIT_DIR`` set the way a git hook sets it, running the exact
    file whose fixture did the damage. Before the conftest strip this turned the victim bare
    and pushed three commits into it. Asserting on conftest's source instead would pass
    against a strip that never executes.
    """
    victim = _victim(tmp_path)
    before_bare, before_log = _bare(victim), _log(victim)

    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_graded_range_includes_own_commits.py",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_clean_env(GIT_DIR=str(victim / ".git")),
        timeout=600,
        check=False,
    )

    assert _bare(victim) in ("false", ""), (
        "pytest under GIT_DIR re-initialized the repository it pointed at as bare\n"
        f"{done.stdout[-2000:]}"
    )
    assert (
        _log(victim) == before_log
    ), f"pytest under GIT_DIR committed into the repository it pointed at\n{done.stdout[-2000:]}"
    assert before_bare == _bare(victim)
    assert done.returncode == 0, (
        "the run failed under GIT_DIR although the repository it pointed at is intact, so the"
        " code under test read that repository instead of its own fixture's:\n"
        f"{done.stdout[-3000:]}"
    )


# ---------------------------------------------------------------------------------------
# The guard: the escape route is closed, but the DAMAGE is watched too.
#
# The conftest strip closes the one route that was found. Watching the repository itself
# closes the ones nobody has thought of: a test that hardcodes the repository path, a helper
# that splats `**{"cwd": ...}` past any static scan, production code called from a test. The
# autouse fixture in tests/conftest.py snapshots the repository's config, HEAD and branch tip
# around every test and aborts the session naming the test that changed them -- the same shape
# as the guards already there for ~/.dream-studio.
# ---------------------------------------------------------------------------------------


def _conftest():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "ds_conftest_under_test", REPO_ROOT / "tests" / "conftest.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ds_conftest_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_the_fingerprint_notices_the_exact_damage_the_escape_did(tmp_path, monkeypatch):
    """core.bare flipping and the branch tip moving are the two observed symptoms."""
    conftest = _conftest()
    victim = _victim(tmp_path)
    monkeypatch.setattr(conftest, "_PLUGIN_ROOT", victim)

    clean = conftest._real_repo_fingerprint()
    assert clean is not None, "the fingerprint could not read the repository, so it guards nothing"
    assert conftest._real_repo_fingerprint() == clean, "the fingerprint is not stable at rest"

    _run(victim, "config", "core.bare", "true")
    assert conftest._real_repo_fingerprint() != clean, "a bare flip went unnoticed"

    _run(victim, "config", "core.bare", "false")
    assert conftest._real_repo_fingerprint() == clean, "the fingerprint did not settle back"

    (victim / "sneaked.txt").write_text("sneaked", encoding="utf-8")
    _run(victim, "add", ".")
    _run(victim, "commit", "-q", "-m", "a commit nobody asked for")
    assert conftest._real_repo_fingerprint() != clean, "a commit on the branch went unnoticed"


def test_the_fingerprint_resolves_a_worktree_whose_dot_git_is_a_file(tmp_path, monkeypatch):
    """A worktree's ``.git`` is a FILE holding ``gitdir:``, and this work happens in worktrees.

    Returning None there would leave the guard silently inert in exactly the place the
    damage was done -- passing, and watching nothing.
    """
    conftest = _conftest()
    victim = _victim(tmp_path)
    linked = tmp_path / "linked"
    assert _run(victim, "worktree", "add", "-q", str(linked), "-b", "side").returncode == 0
    assert (linked / ".git").is_file(), "the worktree's .git should be a file"

    monkeypatch.setattr(conftest, "_PLUGIN_ROOT", linked)
    clean = conftest._real_repo_fingerprint()
    assert clean is not None, "the worktree's .git file was not resolved"

    # core.bare lives in the COMMON config, shared with the main repository -- resolving
    # `commondir` is what makes that reachable from here.
    _run(victim, "config", "core.bare", "true")
    assert conftest._real_repo_fingerprint() != clean, "the shared config is not being watched"


def test_the_guard_aborts_the_session_and_names_the_test_that_did_it(tmp_path):
    """The wiring proof: a real pytest run, and a test that really does damage a repository.

    ``_PLUGIN_ROOT`` is derived from conftest's own location, so a copy of conftest placed in
    a victim repository watches THAT repository. The test below then commits into it -- the
    genuine offence, with nothing stubbed -- and the run must abort naming it. Asserting that
    the fixture contains a call would pass against a guard wired to nothing.
    """
    victim = _victim(tmp_path)
    tests_dir = victim / "tests"
    tests_dir.mkdir()
    (tests_dir / "conftest.py").write_bytes((REPO_ROOT / "tests" / "conftest.py").read_bytes())
    (tests_dir / "test_offender.py").write_text(
        "import subprocess\n"
        "from pathlib import Path\n"
        "VICTIM = Path(__file__).resolve().parent.parent\n"
        "def test_a_test_that_commits_into_the_repository_it_runs_in():\n"
        "    (VICTIM / 'oops.txt').write_text('oops', encoding='utf-8')\n"
        "    subprocess.run(['git', 'add', '.'], cwd=str(VICTIM), check=True)\n"
        "    subprocess.run(\n"
        "        ['git', 'commit', '-q', '-m', 'the offence'], cwd=str(VICTIM), check=True\n"
        "    )\n",
        encoding="utf-8",
    )

    done = subprocess.run(
        [sys.executable, "-m", "pytest", str(tests_dir), "-q", "-p", "no:cacheprovider"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_clean_env(PYTHONPATH=str(REPO_ROOT)),
        timeout=600,
        check=False,
    )

    output = done.stdout + done.stderr
    assert "test_a_test_that_commits_into_the_repository_it_runs_in" in output, (
        "the guard did not name the offending test -- the previous round of this bug cost a"
        f" day of bisecting for exactly that reason\n{output[-3000:]}"
    )
    assert "modified the real git repository" in output, (
        f"the guard did not fire on a test that committed into its own repository\n"
        f"{output[-3000:]}"
    )
    assert done.returncode != 0, "the run should have aborted"
