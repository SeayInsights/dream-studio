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

import pytest

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


# ---------------------------------------------------------------------------------------
# The guard used to blame the test because it had no record of what moved HEAD.
#
# Measured 2026-09-22: four consecutive full-suite runs were killed at ~40%, each naming a
# different innocent test in tests/unit/test_launch_orchestration.py. The real cause was an
# operator committing in another window while the suite ran. The guard saw the repository
# change, knew only which test was executing, and named it -- an accusation built from the
# absence of evidence rather than from evidence.
#
# Three things now form the record: whether THIS test ran a git command (the suite's own
# subprocess calls are recorded), whether the config changed (bare is damage, a moved tip is
# not), and whether git wrote a reflog entry (it always does; a hand-written ref never does).
# ---------------------------------------------------------------------------------------


def _run_pytest_in(tests_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
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


def test_an_external_commit_during_the_run_does_not_abort_or_blame_the_test(tmp_path):
    """The measured false positive, reproduced and fixed.

    The inner test runs no git and simply waits. While it waits, THIS process commits into
    the victim repository -- which is exactly what an operator committing in another window
    looks like to the guard. The run must finish, the innocent test must pass, and the
    notice must say the repository changed without accusing it.
    """
    import threading
    import time

    victim = _victim(tmp_path)
    tests_dir = victim / "tests"
    tests_dir.mkdir()
    (tests_dir / "conftest.py").write_bytes((REPO_ROOT / "tests" / "conftest.py").read_bytes())
    (tests_dir / "test_innocent.py").write_text(
        "import time\n"
        "from pathlib import Path\n"
        "VICTIM = Path(__file__).resolve().parent.parent\n"
        "def test_a_test_that_touches_no_repository_at_all():\n"
        "    (VICTIM / 'tests' / 'running').write_text('yes', encoding='utf-8')\n"
        "    time.sleep(6)\n"
        "    assert True\n",
        encoding="utf-8",
    )

    done: dict[str, subprocess.CompletedProcess] = {}

    def _go():
        done["result"] = _run_pytest_in(tests_dir)

    worker = threading.Thread(target=_go)
    worker.start()

    # Commit into the victim WHILE the innocent test is mid-flight.
    marker = tests_dir / "running"
    for _ in range(200):
        if marker.exists():
            break
        time.sleep(0.1)
    assert marker.exists(), "the inner test never started"
    (victim / "outside.txt").write_text("an operator commit", encoding="utf-8")
    assert _run(victim, "add", "outside.txt").returncode == 0
    assert _run(victim, "commit", "-q", "-m", "a commit made outside the suite").returncode == 0

    worker.join(timeout=600)
    result = done["result"]
    output = result.stdout + result.stderr

    assert result.returncode == 0, (
        "an external commit killed a clean run -- the innocent case must not abort\n"
        f"{output[-3000:]}"
    )
    assert "1 passed" in output, f"the innocent test did not run to completion\n{output[-2000:]}"
    assert (
        "[repo-guard]" in output
    ), f"the change went unreported -- it should be noticed, just not blamed\n{output[-2000:]}"
    assert (
        "modified the real git repository" not in output
    ), f"the guard still accused the test that happened to be running\n{output[-2000:]}"
    assert "a commit made outside the suite" in output, (
        "the notice did not say what moved HEAD, which is the whole point of the reflog"
        f"\n{output[-2000:]}"
    )


def test_a_ref_written_without_git_still_aborts(tmp_path):
    """The hole the subprocess record alone would leave, closed by the reflog.

    A test that hand-writes `.git/refs/heads/<branch>` moves the tip with no git command
    and no reflog entry. That is never an ordinary operator commit, so it must still stop
    the run even though the suite recorded no git call.
    """
    victim = _victim(tmp_path)
    head = (victim / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    ref = head.split(":", 1)[1].strip()

    tests_dir = victim / "tests"
    tests_dir.mkdir()
    (tests_dir / "conftest.py").write_bytes((REPO_ROOT / "tests" / "conftest.py").read_bytes())
    (tests_dir / "test_sneaky.py").write_text(
        "from pathlib import Path\n"
        "VICTIM = Path(__file__).resolve().parent.parent\n"
        f"REF = {ref!r}\n"
        "def test_a_test_that_writes_a_ref_by_hand():\n"
        "    p = VICTIM / '.git' / REF\n"
        "    p.write_text('0' * 40 + chr(10), encoding='utf-8')\n",
        encoding="utf-8",
    )

    result = _run_pytest_in(tests_dir)
    output = result.stdout + result.stderr
    assert (
        result.returncode != 0
    ), f"a ref written behind git's back did not abort\n{output[-3000:]}"
    assert (
        "test_a_test_that_writes_a_ref_by_hand" in output
    ), f"the guard did not name the test that bypassed git\n{output[-3000:]}"
    assert (
        "without going through git" in output
    ), f"the message did not say what made this different from a commit\n{output[-3000:]}"


# ---------------------------------------------------------------------------------------
# Which repository a git call was pointed at, which is not the same as whether one happened.
#
# The first version of the record counted EVERY git call, and the improved failure message
# caught it within one run: a test was blamed for a commit the reflog attributed to the
# operator, on the evidence that it had run `git -C <another repo> tag --sort=...` -- a
# read, against a different repository entirely. Two facts that contradict each other are
# worse than one fact.
#
# Targeting is the discriminator rather than the verb. Sorting subcommands into readers and
# writers is a list that rots the first time git grows a flag; "which repository is this
# pointed at" is answerable from the invocation itself.
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv,cwd,counts,why",
    [
        (["git", "-C", "/somewhere/else", "tag"], None, False, "another repo named by -C"),
        (
            ["git", "--git-dir=/somewhere/else/.git", "log"],
            None,
            False,
            "another repo by --git-dir",
        ),
        (["git", "status"], None, True, "no target: git acts on the process cwd"),
        (["git", "-C", "."], None, True, "the guarded repo named by -C"),
        (["git", "init"], "/tmp/nowhere-near-the-repo", False, "a cwd outside the repo"),
    ],
)
def test_only_a_git_call_aimed_at_the_guarded_repo_counts(argv, cwd, counts, why):
    conftest = _conftest()
    assert conftest._targets_guarded_repo(argv, cwd) is counts, why


def test_a_git_call_whose_target_cannot_be_resolved_counts():
    """Fails SAFE. An unattributable git call is exactly the kind the original escape
    produced -- GIT_DIR pointing somewhere the invocation never mentions."""
    conftest = _conftest()
    assert conftest._targets_guarded_repo(["git", "-C", "\0bad\0path", "status"], None) is True


def test_a_test_reading_another_repository_is_not_blamed_for_an_external_commit(tmp_path):
    """The exact failure observed on a real run, reproduced.

    A test ran `git -C <another repo> tag --sort=-version:refname` -- a READ, against a
    repository that is not the guarded one -- while the operator committed. The guard
    recorded the git call, decided the test was the culprit, and killed a 2,770-test run,
    printing two facts that contradicted each other: the reflog named the operator's commit
    and the evidence named the test's git call.

    This is the end-to-end half of the targeting check. The unit cases above prove
    `_targets_guarded_repo` answers correctly; a mutant that counted every git call
    regardless of target passed all of them, because nothing proved the recorder consults
    it. This does.
    """
    import threading
    import time

    victim = _victim(tmp_path)
    (tmp_path / "other").mkdir()
    elsewhere = _victim(tmp_path / "other")

    tests_dir = victim / "tests"
    tests_dir.mkdir()
    (tests_dir / "conftest.py").write_bytes((REPO_ROOT / "tests" / "conftest.py").read_bytes())
    (tests_dir / "test_reads_elsewhere.py").write_text(
        "import subprocess, time\n"
        "from pathlib import Path\n"
        "VICTIM = Path(__file__).resolve().parent.parent\n"
        f"ELSEWHERE = {str(elsewhere)!r}\n"
        "def test_a_test_that_reads_a_different_repository():\n"
        "    subprocess.run(['git', '-C', ELSEWHERE, 'tag', '--sort=-version:refname'],\n"
        "                   capture_output=True, check=False)\n"
        "    (VICTIM / 'tests' / 'running').write_text('yes', encoding='utf-8')\n"
        "    time.sleep(6)\n",
        encoding="utf-8",
    )

    done: dict[str, subprocess.CompletedProcess] = {}

    def _go():
        done["result"] = _run_pytest_in(tests_dir)

    worker = threading.Thread(target=_go)
    worker.start()

    marker = tests_dir / "running"
    for _ in range(200):
        if marker.exists():
            break
        time.sleep(0.1)
    assert marker.exists(), "the inner test never started"
    (victim / "outside.txt").write_text("an operator commit", encoding="utf-8")
    assert _run(victim, "add", "outside.txt").returncode == 0
    assert _run(victim, "commit", "-q", "-m", "a commit made outside the suite").returncode == 0

    worker.join(timeout=600)
    output = done["result"].stdout + done["result"].stderr

    assert done["result"].returncode == 0, (
        "a test that merely READ another repository was blamed for the operator's commit"
        f"\n{output[-3000:]}"
    )
    assert "[repo-guard]" in output, f"the external change went unreported\n{output[-2000:]}"
    assert (
        "modified the real git repository" not in output
    ), f"the guard still accused the test\n{output[-2000:]}"
