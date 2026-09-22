"""pytest configuration — make `hooks/` importable as a top-level package.

Top-of-file test isolation guard
---------------------------------
DREAM_STUDIO_HOME, DREAM_STUDIO_DB_PATH, and DS_SPOOL_ROOT are set here —
at conftest MODULE IMPORT TIME — before pytest collects tests and before any
test module is imported.

Why this must happen before ``import pytest``:
pytest imports conftest.py first, then imports each test module during
collection. Python executes module-level code at import time. Some production
modules (notably core.config.database.DatabaseRuntime) initialize a singleton
on first use and cache the DB path. If a test module's top-level import chain
reaches DatabaseRuntime before any fixture has a chance to run, the singleton
caches the real operator DB at ~/.dream-studio/state/studio.db.

By setting the env vars here, any DB path resolution that happens at import
time will see the tmp directory instead of the real one.

This resolves B3 from the 2026-05-24 final audit: 9 tests previously
contaminated the real production DB on every pytest run.
"""

from __future__ import annotations

import os as _os
import pathlib as _pathlib
import tempfile as _tempfile

# Record the real DB path for the post-test contamination guard.
_real_home_db = _pathlib.Path.home() / ".dream-studio" / "state" / "studio.db"
_REAL_DB_MTIME_AT_SESSION_START = _real_home_db.stat().st_mtime if _real_home_db.exists() else None

# Only redirect if not already set — lets callers like tox or CI override.
if "DREAM_STUDIO_DB_PATH" not in _os.environ:
    _session_tmp = _pathlib.Path(_tempfile.mkdtemp(prefix="dream-studio-test-"))
    (_session_tmp / "state").mkdir(parents=True, exist_ok=True)
    (_session_tmp / "events").mkdir(parents=True, exist_ok=True)
    (_session_tmp / "events" / "pending").mkdir(parents=True, exist_ok=True)
    (_session_tmp / "events" / "processed").mkdir(parents=True, exist_ok=True)
    _os.environ["DREAM_STUDIO_HOME"] = str(_session_tmp)
    _os.environ["DREAM_STUDIO_DB_PATH"] = str(_session_tmp / "state" / "studio.db")
    _os.environ["DS_SPOOL_ROOT"] = str(_session_tmp / "events")

# Same isolation guard, for git instead of the DB.
#
# git exports GIT_DIR -- pointing at the operator's real repository -- to every hook it runs.
# The pre-push gate runs pytest, pytest's children inherit GIT_DIR, and a fixture that does
# `subprocess.run(["git", "init"], cwd=<tmp>)` then re-initializes THAT repository instead of
# the temporary one: bare, because the cwd is not its work tree. The commits that follow land
# in the real repository too.
#
# Measured before this was added: core.bare on the operator's repository flipped to true six
# times in one session, always after a gate run; the checked-out branch's ref moved on its own;
# and the repository collected `commit a` / `commit b` / `commit c` from a fixture in
# tests/unit/test_graded_range_includes_own_commits.py. Running that file by hand never
# reproduced it, because no GIT_DIR is set outside a hook.
#
# Stripping these makes the under-a-hook environment identical to the ordinary `pytest` one --
# the environment every test already passes in -- so no test loses anything it relied on. A
# test that means to act on a specific repository passes cwd=, which is unaffected.
for _pointer in (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CEILING_DIRECTORIES",
):
    _os.environ.pop(_pointer, None)

# Windows-only: install SIGINT handler before pytest does, so pytest never
# sees the phantom signals that occur on this platform during the ingest
# pipeline's filesystem and SQLite operations. The handler in
# spool/ingestor.py is the production fix; this conftest handler is the
# test-suite-only fix that prevents pytest's own SIGINT machinery from
# printing a KeyboardInterrupt banner after the test summary. CI on Linux
# is unaffected.
import sys as _sys  # noqa: E402

if _sys.platform == "win32":
    import signal as _signal

    def _conftest_sigint_handler(signum, frame):
        # Absorb all SIGINTs during tests. Phantom SIGINTs from Windows + Python 3.12
        # fs/sqlite operations should never propagate to pytest. Real user Ctrl+C
        # in pytest goes through pytest's own signal machinery, not this handler.
        pass

    _signal.signal(_signal.SIGINT, _conftest_sigint_handler)


import importlib.util  # noqa: E402
import sys  # noqa: E402
import types  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_HOOKS_DIR = _PLUGIN_ROOT / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

_PACK_NAMES = ("core", "quality", "analyze", "domains", "meta")


def _find_handler(name: str) -> Path:
    """Search runtime/hooks/*/ then legacy hooks/handlers/ for a handler."""
    for pack in _PACK_NAMES:
        candidate = _PLUGIN_ROOT / "runtime" / "hooks" / pack / f"{name}.py"
        if candidate.is_file():
            return candidate
    legacy = _PLUGIN_ROOT / "hooks" / "handlers" / f"{name}.py"
    if legacy.is_file():
        return legacy
    raise FileNotFoundError(f"handler {name} not found in runtime/hooks or hooks/handlers")


def load_handler(name: str) -> types.ModuleType:
    """Import a handler by filename stem (e.g. 'on-pulse' -> on_pulse module)."""
    handler_path = _find_handler(name)
    module_name = f"handlers_{name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    assert spec and spec.loader, f"cannot load handler {name}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def reviewed_verdict(verdict: dict | None = None, **fields) -> dict:
    """A review verdict carrying the provenance `independent_review` requires.

    WO 175299fc. The close gate refuses a verdict whose `round_table.seats` is empty
    BEFORE it looks at `passed`, `summary` or anything else -- a score with no lens is a
    score with no provenance. Every synthetic verdict written before that gate landed is
    therefore refused for the missing section and never reaches the behaviour its test was
    written to pin, which is how eighteen tests went red across eight files and held main's
    Full CI red for seven consecutive merges.

    DEFINED ONCE, HERE, because the alternative is the failure this repo keeps paying for:
    the same stub pasted into six files, drifting apart the next time the contract moves.
    `from conftest import reviewed_verdict` is the pattern `load_handler` already
    establishes. When the gate's requirement changes again, this is the single place.

    NOT A BYPASS. It supplies the shape a real verdict carries, so a test asserting on
    `passed` or on partial-write recovery exercises the path it names. The gate's OTHER
    accepted shape -- an operator attestation, exempted because demanding a table would
    block attestation or invite convening one nobody read -- is deliberately not produced
    here: a test wanting that path should build it explicitly, since the exemption is the
    thing under test in those cases.
    """
    seats = [
        {"seat": "Claim and closure auditor", "lane": "a-finding-already-filed", "verdict": "pass"}
    ]
    out: dict = {"round_table": {"seats": seats}}
    out.update(verdict or {})
    out.update(fields)
    return out


def _repo_git_dir() -> Path | None:
    """The real repository's git directory, or None when there isn't one to protect.

    A worktree's ``.git`` is a FILE holding ``gitdir: <path>``, not a directory -- and a
    worktree is exactly where this work gets done, so resolving it is not an edge case.
    """
    dot = _PLUGIN_ROOT / ".git"
    if dot.is_dir():
        return dot
    if dot.is_file():
        try:
            text = dot.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if text.startswith("gitdir:"):
            resolved = Path(text.split(":", 1)[1].strip())
            if resolved.is_dir():
                return resolved
    return None


def _real_repo_fingerprint() -> tuple[bytes, ...] | None:
    """What the escape changed: `core.bare` in the config, HEAD, and the branch tip.

    File reads only, no subprocess -- this runs before and after EVERY test, and a `git`
    invocation per test would cost minutes across the suite.

    Returns None when anything is unreadable, which disables the check rather than failing
    the run: a guard that aborts a session because it could not read a file is worse than
    the escape it watches for.
    """
    git_dir = _repo_git_dir()
    if git_dir is None:
        return None
    commondir = git_dir / "commondir"
    common = git_dir
    if commondir.is_file():
        try:
            common = (git_dir / commondir.read_text(encoding="utf-8").strip()).resolve()
        except OSError:
            return None
    parts: list[bytes] = []
    for candidate in (common / "config", git_dir / "HEAD"):
        try:
            parts.append(candidate.read_bytes())
        except OSError:
            return None
    head = parts[-1].decode("utf-8", "replace").strip()
    if head.startswith("ref:"):
        ref = head.split(":", 1)[1].strip()
        loose = git_dir / ref
        try:
            parts.append(loose.read_bytes() if loose.is_file() else b"<packed>")
        except OSError:
            return None
    return tuple(parts)


def _repo_reflog_tail(size_before: int) -> list[str]:
    """The reflog lines written since `size_before` bytes — what actually moved HEAD.

    Git records every HEAD movement with the operation that caused it (`commit:`,
    `checkout:`, `reset:`, `rebase (finish):`). The guard below used to detect that HEAD
    had moved and have no idea what moved it, so it named the only actor it knew about —
    the test that happened to be running. That is an accusation built from absence of
    evidence, and it is wrong whenever anything outside the suite commits.

    File read only, and only on the failure path, so the per-test cost stays zero.
    """
    git_dir = _repo_git_dir()
    if git_dir is None:
        return []
    commondir = git_dir / "commondir"
    common = git_dir
    if commondir.is_file():
        try:
            common = (git_dir / commondir.read_text(encoding="utf-8").strip()).resolve()
        except OSError:
            return []
    log = common / "logs" / "HEAD"
    try:
        with log.open("rb") as fh:
            fh.seek(max(0, size_before))
            new = fh.read().decode("utf-8", "replace")
    except OSError:
        return []
    out = []
    for line in new.splitlines():
        # <old> <new> <who> <when>\t<operation>: <message>
        message = line.partition("\t")[2]
        if message:
            out.append(message.strip())
    return out


def _repo_reflog_size() -> int:
    """Bytes in the reflog now, so the tail above can be read back on failure."""
    git_dir = _repo_git_dir()
    if git_dir is None:
        return 0
    commondir = git_dir / "commondir"
    common = git_dir
    if commondir.is_file():
        try:
            common = (git_dir / commondir.read_text(encoding="utf-8").strip()).resolve()
        except OSError:
            return 0
    try:
        return (common / "logs" / "HEAD").stat().st_size
    except OSError:
        return 0


def _targets_guarded_repo(argv: list, cwd: object) -> bool:
    """Could this git invocation have acted on the repository the guard watches?

    THE FIRST VERSION COUNTED EVERY GIT CALL, and the improved failure message caught it
    within one run: a test was blamed for a commit the reflog attributed to the operator,
    on the evidence that it had run `git -C <another-checkout> tag
    --sort=-version:refname` -- a read, against a different repository entirely. Two facts
    that contradict each other are worse than one fact, so the record has to be about the
    right repository.

    Targeting is the discriminator rather than the verb. Sorting git subcommands into
    readers and writers would be a list that rots the first time git grows a flag, while
    "which repository is this pointed at" is answerable from the invocation itself.

    Fails SAFE: an invocation whose target cannot be resolved counts, because an
    unattributable git call is exactly the kind the original escape produced.
    """
    tokens = [str(x) for x in argv]
    explicit: list[str] = []
    for i, token in enumerate(tokens):
        if token == "-C" and i + 1 < len(tokens):
            explicit.append(tokens[i + 1])
        elif token.startswith("--git-dir="):
            explicit.append(token.split("=", 1)[1])
        elif token.startswith("--work-tree="):
            explicit.append(token.split("=", 1)[1])

    candidates = explicit or ([str(cwd)] if cwd is not None else [])
    if not candidates:
        # No explicit target and no cwd: git acts on the process's working directory,
        # which under pytest is the guarded repository.
        return True

    for candidate in candidates:
        try:
            resolved = Path(candidate).resolve()
        except (OSError, ValueError):
            return True  # unresolvable: fail safe
        if resolved == _PLUGIN_ROOT or _PLUGIN_ROOT in resolved.parents:
            return True
    return False


class _GitCallRecorder:
    """Whether THIS test ran a git command that could have moved the real repo.

    The second half of the record. `subprocess.run` goes through `Popen`, so wrapping
    the class once catches every route a test could take. It records argv only — no
    behaviour change, no cost beyond an attribute swap per test.

    A test that moved HEAD ran git to do it. A test that ran none did not, and the
    repository was changed by something else — an operator committing while the suite
    runs, an editor, another agent. Those are different events and deserve different
    messages.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._original = None

    def __enter__(self) -> "_GitCallRecorder":
        import subprocess as _sp

        self._original = _sp.Popen
        recorder = self

        class _Recording(_sp.Popen):  # type: ignore[misc]
            def __init__(self, args, *a, **kw):
                try:
                    argv = args if isinstance(args, (list, tuple)) else [args]
                    program = str(argv[0]) if argv else ""
                    if "git" in _os.path.basename(program).lower():
                        if _targets_guarded_repo(argv, kw.get("cwd")):
                            recorder.calls.append(" ".join(str(x) for x in argv)[:200])
                except Exception:
                    pass
                super().__init__(args, *a, **kw)

        _sp.Popen = _Recording  # type: ignore[assignment]
        return self

    def __exit__(self, *exc) -> None:
        import subprocess as _sp

        if self._original is not None:
            _sp.Popen = self._original  # type: ignore[assignment]
        return None


def pytest_configure(config):
    """Reinstall our SIGINT handler after pytest installs its own.

    Pytest registers its own SIGINT handler during configure. This hook runs
    after that, letting us reclaim the handler slot so phantom signals during
    test execution don't reach pytest's machinery. Windows-only.
    """
    if _sys.platform == "win32":
        _signal.signal(_signal.SIGINT, _conftest_sigint_handler)


@pytest.fixture
def handler() -> Any:
    return load_handler


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Redirect HOME, Path.home, and CLAUDE_PROJECTS_DIR to a temp dir."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECTS_DIR", raising=False)
    monkeypatch.delenv("DREAM_STUDIO_HOME", raising=False)
    return tmp_path


import warnings  # noqa: E402


@pytest.fixture(autouse=True)
def reset_warnings():
    warnings.resetwarnings()
    yield


@pytest.fixture(autouse=True)
def default_verify_mock(monkeypatch):
    """WO-GRADER-ADVERSARIAL: independent review is default-on at close, so any
    test that closes a non-documentation WO now runs verify inline. Default the
    grader to the deterministic mock so the suite stays hermetic — no test may
    spawn a real grader CLI as a side effect of closing a WO. Tests that
    exercise real grader resolution or unreviewable flows pop/override
    DREAM_STUDIO_VERIFY_MOCK inside the test body (the established pattern in
    test_wo_verify, test_grader_lookup_unreviewable, et al.).
    """
    if "DREAM_STUDIO_VERIFY_MOCK" not in _os.environ:
        monkeypatch.setenv("DREAM_STUDIO_VERIFY_MOCK", "1")


@pytest.fixture(autouse=True)
def restore_stdin():
    """Snapshot and restore ``sys.stdin`` around every test.

    Some tests replace ``sys.stdin`` (e.g. with ``io.StringIO``) and "restore"
    it to ``sys.__stdin__`` — the real console stream, whose ``isatty()`` is
    True on Windows. That leaked tty-like stdin crosses into later tests and
    makes CLI code paths that gate on ``sys.stdin.isatty()`` (notably
    ``ds work-order start``'s no-brief confirmation prompt) mis-detect an
    interactive operator and abort early — surfacing as an order-dependent
    failure of an unrelated test (WO c2d21490). Restoring to the pre-test
    value (pytest's captured stdin) keeps the leak from crossing test
    boundaries regardless of how a test mutates stdin.
    """
    saved = sys.stdin
    yield
    sys.stdin = saved


@pytest.fixture
def spool_root(tmp_path, monkeypatch):
    """Isolated per-test spool root. Sets DS_SPOOL_ROOT via monkeypatch.setenv so subprocess emitters inherit it."""
    spool = tmp_path / "events"
    spool.mkdir()
    monkeypatch.setenv("DS_SPOOL_ROOT", str(spool))
    yield spool
    # Cleanup uses per-file unlink instead of shutil.rmtree to avoid a
    # Windows + Python 3.12 issue where rmtree's internal lstat call on
    # a just-written .sessions directory delivers a spurious SIGINT.
    sessions = spool / ".sessions"
    if sessions.exists():
        for session_file in sessions.glob("*.json"):
            try:
                session_file.unlink()
            except OSError:
                pass


@pytest.fixture
def ds_home(tmp_path, monkeypatch):
    """Isolated per-test dream-studio home. Sets DS_DREAM_STUDIO_HOME so
    integrations/manifest.py and related modules never reach real ~/.dream-studio."""
    home = tmp_path / "ds_home"
    home.mkdir()
    monkeypatch.setenv("DS_DREAM_STUDIO_HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def guard_real_homedir(tmp_path, monkeypatch, request):
    """Auto-use: ensures no test writes to real ~/.dream-studio or ~/.claude.

    If DS_SPOOL_ROOT is not already set by a test's spool_root fixture, this
    fixture sets a fallback so spool.config.get_spool_root() never reaches ~.
    If DS_DREAM_STUDIO_HOME is not already set, sets a fallback so integration
    manifest writes never reach real ~/.dream-studio/integrations/.
    If DREAM_STUDIO_DB_PATH is not already set, sets a fallback so the
    canonical DB-path resolver (`core.config.database._default_db_path`) and
    every caller that delegates to it write to a hermetic tmp DB instead of
    the operator's real ~/.dream-studio/state/studio.db.
    If DS_ACTIVE_TASK_PATH is not already set, sets a fallback so active task
    writes never reach the real ~/.dream-studio/state/active_task.json.
    """
    if "DS_SPOOL_ROOT" not in _os.environ:
        guard = tmp_path / "guard_spool"
        guard.mkdir()
        monkeypatch.setenv("DS_SPOOL_ROOT", str(guard))

    if "DS_DREAM_STUDIO_HOME" not in _os.environ:
        guard_ds = tmp_path / "guard_ds_home"
        guard_ds.mkdir()
        monkeypatch.setenv("DS_DREAM_STUDIO_HOME", str(guard_ds))

    if "DREAM_STUDIO_DB_PATH" not in _os.environ:
        guard_db_dir = tmp_path / "guard_state"
        guard_db_dir.mkdir()
        monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(guard_db_dir / "studio.db"))

    if "DS_PLATFORM_PROFILE_PATH" not in _os.environ:
        guard_platform_dir = tmp_path / "guard_platform"
        guard_platform_dir.mkdir()
        monkeypatch.setenv("DS_PLATFORM_PROFILE_PATH", str(guard_platform_dir / "platform.json"))

    if "DS_ACTIVE_TASK_PATH" not in _os.environ:
        guard_at_dir = tmp_path / "guard_active_task"
        guard_at_dir.mkdir()
        monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(guard_at_dir / "active_task.json"))

    if "DS_MACHINE_ID_PATH" not in _os.environ:
        guard_mid_dir = tmp_path / "guard_machine_id"
        guard_mid_dir.mkdir()
        monkeypatch.setenv("DS_MACHINE_ID_PATH", str(guard_mid_dir / "machine_id"))

    if "DS_CWD_RESOLVER_ROOT" not in _os.environ:
        monkeypatch.setenv("DS_CWD_RESOLVER_ROOT", str(tmp_path))

    if "DS_DIAGNOSTICS_DIR" not in _os.environ:
        guard_diag_dir = tmp_path / "guard_diagnostics"
        guard_diag_dir.mkdir()
        monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(guard_diag_dir))

    # Reset machine_id process-level cache so each test gets a fresh hermetic ID.
    try:
        import core.telemetry.machine_id as _mid_mod

        _mid_mod._reset_cache()
    except Exception:
        pass

    # Reset DatabaseRuntime singleton so it re-initializes from the (now-patched)
    # DREAM_STUDIO_DB_PATH. Without this, a singleton initialized before the fixture
    # activates caches the real DB path and bypasses the monkeypatch entirely.
    try:
        from core.config.database import DatabaseRuntime as _DBRuntime

        _DBRuntime.reset_instance()
    except Exception:
        pass

    real_events = Path.home() / ".dream-studio" / "events"
    _before_events_mtime = real_events.stat().st_mtime if real_events.exists() else None
    real_integrations = Path.home() / ".dream-studio" / "integrations"
    _before_int_mtime = real_integrations.stat().st_mtime if real_integrations.exists() else None
    real_db = Path.home() / ".dream-studio" / "state" / "studio.db"

    # Only snapshot real DB mtime when DREAM_STUDIO_DB_PATH is NOT redirected away
    # from the real DB. When the top-of-conftest block has redirected it to a session
    # tmp dir, the spool ingestor (a background process) continuously writes real
    # operator events to the real DB — mtime would change regardless of test activity,
    # producing false positives. Trust the env-var redirect as the isolation boundary.
    _real_db_path = str(real_db.resolve())
    _db_path_env = _os.environ.get("DREAM_STUDIO_DB_PATH", "")
    _db_redirected = _db_path_env and _db_path_env != _real_db_path
    _before_db_mtime = (
        (real_db.stat().st_mtime if real_db.is_file() else None) if not _db_redirected else None
    )

    # The same guard, for the operator's git repository. A test that reaches it does not
    # leave an mtime to compare -- it leaves a repository that is bare, or a branch pointing
    # somewhere nobody moved it. See the GIT_DIR note at the top of this file for the escape
    # this watches; that strip closes the known route, and this catches a route nobody has
    # thought of yet, by watching the damage instead of the mechanism.
    _before_repo = _real_repo_fingerprint()
    _before_reflog = _repo_reflog_size()

    # WHAT MOVED HEAD, recorded rather than inferred. See `_GitCallRecorder`.
    _git_calls = _GitCallRecorder()
    _git_calls.__enter__()

    try:
        yield
    finally:
        _git_calls.__exit__(None, None, None)

    # Teardown: reset singleton again so subsequent tests don't inherit a stale instance
    # pointing at the (now-cleaned-up) tmp DB path.
    try:
        from core.config.database import DatabaseRuntime as _DBRuntime

        _DBRuntime.reset_instance()
    except Exception:
        pass

    if _before_events_mtime is not None and real_events.exists():
        if real_events.stat().st_mtime != _before_events_mtime:
            pytest.exit(
                # NAME THE TEST. This guard runs per test, so its teardown already knows
                # which one polluted -- it just did not say, and the message ended a
                # 5,928-test session with no way to tell who did it. Bisecting ~2,400
                # tests by hand is the cost of a missing identifier (WO efe2ce9d).
                f"FATAL: {request.node.nodeid} modified real ~/.dream-studio/events. "
                "Use the spool_root fixture. Aborting session to prevent further damage.",
                returncode=2,
            )
    if _before_int_mtime is not None and real_integrations.exists():
        if real_integrations.stat().st_mtime != _before_int_mtime:
            pytest.exit(
                f"FATAL: {request.node.nodeid} modified real ~/.dream-studio/integrations. "
                "Use the ds_home fixture. Aborting session to prevent further damage.",
                returncode=2,
            )
    # Only check real DB mtime when the redirect is NOT in place (fallback safety).
    # With the redirect active, the spool ingestor writes legitimately to the real DB
    # and any mtime check here would be a false positive.
    if _before_db_mtime is not None and real_db.is_file():
        if real_db.stat().st_mtime != _before_db_mtime:
            pytest.exit(
                f"FATAL: Test wrote to real production DB at {real_db}. "
                "DREAM_STUDIO_DB_PATH was not redirected at fixture time — "
                "this indicates the top-of-conftest isolation block did not run. "
                "Aborting session to prevent further damage.",
                returncode=2,
            )
    _after_repo = _real_repo_fingerprint()
    if _before_repo is not None and _after_repo != _before_repo:
        # WAS IT DAMAGED, OR MERELY MOVED? The escape this guard was built for turned the
        # repository BARE -- a change to `core.bare` in the config, which is the first
        # element of the fingerprint. A branch tip moving is an ordinary commit. Those are
        # different events and only one of them is damage.
        _config_changed = (
            _after_repo is None or not _after_repo or _after_repo[0] != _before_repo[0]
        )
        _operations = _repo_reflog_tail(_before_reflog)
        _what = "; ".join(_operations[:3]) if _operations else "no reflog entry"

        # THE REFLOG IS THE THIRD PIECE OF EVIDENCE, and it closes the hole the other two
        # leave. Git writes a reflog entry for every HEAD movement it makes; a test that
        # hand-writes `.git/refs/heads/<branch>` or `.git/HEAD` in Python moves the tip and
        # leaves NO entry. So "the fingerprint changed and the reflog did not grow" means
        # something bypassed git entirely, which is never an ordinary operator commit and
        # always worth stopping for.
        if _config_changed or _git_calls.calls or not _operations:
            # The test ran git against a real repository, or the repository is damaged
            # rather than moved. NAME THE TEST -- the previous round of this bug cost six
            # repository repairs and a day of bisecting precisely because nothing said who.
            if _git_calls.calls:
                _by = f" It ran: {_git_calls.calls[0]}"
            elif _config_changed:
                _by = " Its config changed, which is damage rather than an ordinary commit."
            else:
                _by = (
                    " Nothing was written to the reflog, so the refs were changed without"
                    " going through git at all."
                )
            pytest.exit(
                f"FATAL: {request.node.nodeid} modified the real git repository at "
                f"{_PLUGIN_ROOT} (reflog says: {_what}).{_by} "
                "A test must operate on a temporary repository: pass cwd=<tmp> AND an env "
                "with GIT_DIR/GIT_WORK_TREE removed. Aborting session to prevent further "
                "damage.",
                returncode=2,
            )

        # THE SUITE IS INNOCENT AND THE RUN CONTINUES. This test ran no git command and the
        # repository is not damaged -- its HEAD or branch tip moved while the suite was
        # running, which is what happens when the operator commits in another window.
        # Killing a clean run on that evidence loses thousands of passing tests and teaches
        # the reader that this guard cries wolf. The next test re-baselines on setup, so
        # nothing is carried forward.
        _notice = (
            f"[repo-guard] The repository at {_PLUGIN_ROOT} changed during "
            f"{request.node.nodeid}, but that test ran no git command against it and the "
            f"repository is not damaged. Reflog says: {_what}. Treating this as an external "
            "change (an operator commit during the run is the usual cause) and continuing."
        )
        # THROUGH THE TERMINAL REPORTER, not print(). pytest captures stdout and stderr per
        # test and discards them when it passes, so a print here would be visible only on
        # the runs where nothing was wrong -- a notice recorded where nobody reads it, which
        # is the shape this guard exists to avoid. Found by the test below asserting that
        # the notice actually reaches the operator.
        _reporter = request.config.pluginmanager.get_plugin("terminalreporter")
        if _reporter is not None:
            _reporter.write_line(_notice)
        else:
            print(_notice, file=_sys.stderr)
