"""on-session-end hands the learning-loop analyzers to a detached worker.

The Stop hook used to run them inline. WorkflowPatternAnalyzer scans every row of the
events table (525k rows, 1.5 GB on the operator's machine) and was measured past three
minutes, so every turn ended in a hang. Because the "session ended" sentinel is written
only after end_session returns, a killed run left no marker and the next turn started
the same scan again; stuck dispatcher processes were found 63 minutes old.

These tests pin the three properties that fix it: the Stop path does no analysis, the
worker cannot be waited on, and a killed worker cannot cause a retry loop.
"""

from __future__ import annotations

import importlib.util
import inspect
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
_HOOK = REPO / "runtime" / "hooks" / "meta" / "on-session-end.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("on_session_end_under_test", _HOOK)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


hook = _load_module()


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point the hook's state and diagnostics at a temp dir, and never spawn for real."""
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(hook.paths, "state_dir", lambda: state)
    monkeypatch.setattr(hook.paths, "home_dir", lambda: tmp_path)
    monkeypatch.delenv("DS_SESSION_ANALYSIS", raising=False)
    # A test that reaches the real analyzers must find an empty database, never the
    # operator's: they scan every event row and upsert derived signals.
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(tmp_path / "studio.db"))
    return tmp_path


def _stdin(monkeypatch, payload: dict) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))


# --- the Stop path does no analysis -------------------------------------------------


def test_end_session_itself_runs_no_analyzer():
    """The guard against re-inlining: any caller of end_session is on the Stop path, so
    an analyzer named in its source is a hang waiting to come back."""
    from core.event_store import studio_db

    source = inspect.getsource(studio_db.end_session)
    for analyzer in (
        "FrictionSignalHarvester",
        "GapClassifier",
        "WorkflowPatternAnalyzer",
        "RetroactiveValidator",
    ):
        assert analyzer not in source, f"{analyzer} is back inside end_session()"


def test_stop_path_enqueues_and_spawns_but_never_analyses(home, monkeypatch):
    spawned: list[int] = []
    monkeypatch.setattr(hook, "has_sentinel", lambda key: False)
    monkeypatch.setattr(hook, "set_sentinel", lambda key, kind: True)
    monkeypatch.setattr(hook, "end_session", lambda *a, **kw: True)
    monkeypatch.setattr(hook, "_spawn_worker", lambda: spawned.append(1))

    def _must_not_run(*a, **kw):
        raise AssertionError("the Stop hook ran the analyzers inline")

    monkeypatch.setattr(hook, "run_session_end_analyzers", _must_not_run)
    _stdin(monkeypatch, {"session_id": "s-1"})

    hook.main()

    assert spawned == [1]
    assert hook._claim_pending() == ["s-1"]


def test_a_session_whose_row_did_not_close_is_not_queued(home, monkeypatch):
    spawned: list[int] = []
    monkeypatch.setattr(hook, "has_sentinel", lambda key: False)
    monkeypatch.setattr(hook, "set_sentinel", lambda key, kind: True)
    monkeypatch.setattr(hook, "end_session", lambda *a, **kw: False)
    monkeypatch.setattr(hook, "_spawn_worker", lambda: spawned.append(1))
    _stdin(monkeypatch, {"session_id": "s-2"})

    hook.main()

    assert spawned == []
    assert hook._claim_pending() == []


def test_an_already_ended_session_queues_nothing(home, monkeypatch):
    spawned: list[int] = []
    monkeypatch.setattr(hook, "has_sentinel", lambda key: True)
    monkeypatch.setattr(hook, "_spawn_worker", lambda: spawned.append(1))
    _stdin(monkeypatch, {"session_id": "s-3"})

    hook.main()

    assert spawned == []
    assert hook._claim_pending() == []


def test_a_failed_handoff_is_recorded_not_raised(home, monkeypatch):
    """The hook may not raise, but it may not fail without a trace either."""
    monkeypatch.setattr(hook, "has_sentinel", lambda key: False)
    monkeypatch.setattr(hook, "set_sentinel", lambda key, kind: True)
    monkeypatch.setattr(hook, "end_session", lambda *a, **kw: True)

    def _boom():
        raise OSError("cannot start a process")

    monkeypatch.setattr(hook, "_spawn_worker", _boom)
    _stdin(monkeypatch, {"session_id": "s-4"})

    hook.main()  # must not raise

    log = (home / "diagnostics" / "session-analyzers.log").read_text(encoding="utf-8")
    assert "s-4" in log and "cannot start a process" in log


# --- the worker cannot be waited on -------------------------------------------------


def test_spawn_is_detached_and_inherits_no_pipe(home, monkeypatch):
    """Claude Code waits for the hook's stdout to reach EOF. A child that inherited that
    pipe would hold the turn open exactly as the inline scan did."""
    seen: dict = {}

    class _Popen:
        def __init__(self, cmd, **kwargs):
            seen["cmd"], seen["kwargs"] = cmd, kwargs

    monkeypatch.setattr(hook.subprocess, "Popen", _Popen)

    hook._spawn_worker()

    kwargs = seen["kwargs"]
    for stream in ("stdin", "stdout", "stderr"):
        assert kwargs[stream] is subprocess.DEVNULL, f"{stream} is not redirected"
    assert kwargs["close_fds"] is True
    assert seen["cmd"][-1] == "--analyze"
    if os.name == "nt":
        assert kwargs["creationflags"] & subprocess.DETACHED_PROCESS
        assert kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert kwargs["start_new_session"] is True


def test_spawn_falls_back_when_the_job_forbids_breakaway(home, monkeypatch):
    if os.name != "nt":
        pytest.skip("job objects are a Windows mechanism")
    attempts: list[int] = []

    class _Popen:
        def __init__(self, cmd, **kwargs):
            attempts.append(kwargs["creationflags"])
            if len(attempts) == 1:
                raise OSError("access denied")

    monkeypatch.setattr(hook.subprocess, "Popen", _Popen)

    hook._spawn_worker()

    assert len(attempts) == 2, "a refused breakaway must retry detached, not give up"
    assert attempts[1] & subprocess.DETACHED_PROCESS


def test_the_switch_turns_off_the_queue_as_well_as_the_spawn(home, monkeypatch):
    """With only the spawn disabled, sessions were still queued and nothing drained them,
    so the pending directory grew for ever."""
    monkeypatch.setenv("DS_SESSION_ANALYSIS", "0")
    monkeypatch.setattr(hook, "has_sentinel", lambda key: False)
    monkeypatch.setattr(hook, "set_sentinel", lambda key, kind: True)
    monkeypatch.setattr(hook, "end_session", lambda *a, **kw: True)
    monkeypatch.setattr(hook.subprocess, "Popen", lambda *a, **kw: pytest.fail("spawned"))
    _stdin(monkeypatch, {"session_id": "s-off"})

    hook.main()

    assert not hook._has_pending()


def test_a_malformed_interval_does_not_stop_the_hook_importing(monkeypatch):
    """The interval is read at import, before the hook closes the session row. "6h" raised
    ValueError there and took the whole hook down."""
    monkeypatch.setenv("DS_PATTERN_ANALYSIS_MIN_INTERVAL_S", "6h")
    reloaded = _load_module()
    assert reloaded._PATTERN_MIN_INTERVAL_S == 6 * 3600


# --- a killed worker cannot cause a retry loop --------------------------------------


def test_a_session_is_claimed_before_it_is_analysed(home, monkeypatch):
    """Claim-first. The worker that is killed mid-scan has already taken its sessions off
    the queue, so the next turn does not start the same scan again."""
    hook._enqueue("a")
    hook._enqueue("b")
    seen_pending: list[bool] = []

    def _analyse(ids, pattern_analysis):
        seen_pending.append(hook._has_pending())

    monkeypatch.setattr(hook, "run_session_end_analyzers", _analyse)

    assert hook.run_worker() == 0

    assert seen_pending == [False], "sessions were still queued while being analysed"


def test_a_failing_analysis_is_recorded_and_not_retried(home, monkeypatch):
    hook._enqueue("a")
    calls: list[list[str]] = []

    def _analyse(ids, pattern_analysis):
        calls.append(list(ids))
        raise RuntimeError("scan blew up")

    monkeypatch.setattr(hook, "run_session_end_analyzers", _analyse)

    assert hook.run_worker() == 0

    assert calls == [["a"]], "a failed batch must not be retried by the same worker"
    assert not hook._has_pending()
    assert "scan blew up" in (home / "diagnostics" / "session-analyzers.log").read_text(
        encoding="utf-8"
    )
    assert not hook._lock_path().exists(), "the lock must be released after a failure"


def test_every_pending_session_is_analysed_in_one_batch(home, monkeypatch):
    for sid in ("a", "b", "c"):
        hook._enqueue(sid)
    batches: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(
        hook,
        "run_session_end_analyzers",
        lambda ids, pattern_analysis: batches.append((sorted(ids), pattern_analysis)),
    )

    hook.run_worker()

    assert batches == [(["a", "b", "c"], True)]


def test_an_undecodable_queue_file_does_not_block_the_sessions_behind_it(home, monkeypatch):
    """A file that is not UTF-8 sorts first and used to raise out of the worker on every
    run, so no later session was ever analysed."""
    pending = home / "state" / "session-analysis-pending"
    pending.mkdir(parents=True)
    (pending / "0000000000000000").write_bytes(bytes([0xFF, 0xFE, 0x80]) + b" not utf8")
    hook._enqueue("good")
    batches: list[list[str]] = []
    monkeypatch.setattr(
        hook, "run_session_end_analyzers", lambda ids, pattern_analysis: batches.append(list(ids))
    )

    assert hook.run_worker() == 0

    assert batches == [["good"]]
    assert not hook._has_pending(), "the poison file must be dropped, not re-read for ever"


# --- one worker at a time -----------------------------------------------------------


def test_a_second_worker_yields_to_a_live_one(home, monkeypatch):
    hook._enqueue("a")
    hook._lock_path().write_text("12345", encoding="utf-8")
    monkeypatch.setattr(
        hook, "run_session_end_analyzers", lambda *a, **kw: pytest.fail("ran beside the holder")
    )

    assert hook.run_worker() == 0

    assert hook._has_pending(), "the holder is responsible for draining this session"
    assert hook._lock_path().exists(), "a yielding worker must not remove another's lock"


def test_two_workers_cannot_both_steal_a_stale_lock(home, monkeypatch):
    """The steal is a rename, which is atomic: the loser finds the lock already gone and
    retries instead of crashing or running beside the winner."""
    hook._enqueue("a")
    lock = hook._lock_path()
    lock.write_text("12345", encoding="utf-8")
    long_ago = time.time() - hook._LOCK_STALE_S - 60
    os.utime(lock, (long_ago, long_ago))
    real_replace = os.replace

    def _lose_the_race(src, dst):
        Path(src).unlink()  # the other worker took it between our stat and our rename
        return real_replace(src, dst)  # -> FileNotFoundError

    monkeypatch.setattr(hook.os, "replace", _lose_the_race)
    batches: list[list[str]] = []
    monkeypatch.setattr(
        hook, "run_session_end_analyzers", lambda ids, pattern_analysis: batches.append(list(ids))
    )

    assert hook.run_worker() == 0

    assert batches == [["a"]], "after losing the steal the worker must retry and take the lock"


def test_a_live_worker_keeps_its_lock_fresh_however_long_the_scan_runs(home, monkeypatch):
    """The stale window is minutes, but one scan can run for longer. The heartbeat is what
    stops a second worker stealing the lock from under a scan that is still running."""
    monkeypatch.setattr(hook, "_HEARTBEAT_S", 0.05)
    hook._enqueue("a")
    mtimes: list[float] = []

    def _slow_scan(ids, pattern_analysis):
        lock = hook._lock_path()
        old = time.time() - 300  # as if the last beat were five minutes ago
        os.utime(lock, (old, old))
        deadline = time.time() + 5
        while time.time() < deadline and lock.stat().st_mtime < time.time() - 60:
            time.sleep(0.02)
        mtimes.append(lock.stat().st_mtime)

    monkeypatch.setattr(hook, "run_session_end_analyzers", _slow_scan)

    hook.run_worker()

    assert mtimes and mtimes[0] > time.time() - 60, "the heartbeat never refreshed the lock"


def test_a_dead_workers_lock_is_stolen(home, monkeypatch):
    hook._enqueue("a")
    lock = hook._lock_path()
    lock.write_text("12345", encoding="utf-8")
    long_ago = time.time() - hook._LOCK_STALE_S - 60
    os.utime(lock, (long_ago, long_ago))
    batches: list[list[str]] = []
    monkeypatch.setattr(
        hook, "run_session_end_analyzers", lambda ids, pattern_analysis: batches.append(list(ids))
    )

    hook.run_worker()

    assert batches == [["a"]]
    assert not lock.exists()


# --- the global scan is throttled ---------------------------------------------------


def test_the_global_scan_runs_once_per_interval_not_once_per_session(home, monkeypatch):
    patterns: list[bool] = []
    monkeypatch.setattr(
        hook,
        "run_session_end_analyzers",
        lambda ids, pattern_analysis: patterns.append(pattern_analysis),
    )

    hook._enqueue("a")
    hook.run_worker()
    hook._enqueue("b")
    hook.run_worker()

    assert patterns == [True, False]


def test_the_slot_is_stamped_before_the_scan_so_a_killed_scan_is_not_retried(home, monkeypatch):
    stamped_during_scan: list[bool] = []
    marker = home / "state" / "pattern-analysis.last"
    monkeypatch.setattr(
        hook,
        "run_session_end_analyzers",
        lambda ids, pattern_analysis: stamped_during_scan.append(marker.exists()),
    )
    hook._enqueue("a")

    hook.run_worker()

    assert stamped_during_scan == [True]


# --- the real entry point boots as a script -----------------------------------------


def test_the_analyze_entry_point_runs_as_a_detached_script_would(tmp_path):
    """A unit test with the spawn stubbed cannot tell you the worker starts. This launches
    it the way _spawn_worker does -- a fresh interpreter running the file with --analyze,
    code found through PYTHONPATH -- against an empty home, and checks it consumed its
    queue and released its lock."""
    state = tmp_path / "state"
    pending = state / "session-analysis-pending"
    pending.mkdir(parents=True)
    (pending / "x").write_text("subprocess-session", encoding="utf-8")
    env = {
        **os.environ,
        "DREAM_STUDIO_HOME": str(tmp_path),
        "DREAM_STUDIO_DB_PATH": str(tmp_path / "studio.db"),
        "PYTHONPATH": os.pathsep.join([str(REPO), os.environ.get("PYTHONPATH", "")]),
    }

    done = subprocess.run(
        [sys.executable, "-X", "utf8", str(_HOOK), "--analyze"],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )

    assert done.returncode == 0, done.stderr
    assert not list(pending.glob("*")), "the worker did not consume its queue"
    assert not (state / "session-analyzers.lock").exists(), "the worker left its lock behind"
