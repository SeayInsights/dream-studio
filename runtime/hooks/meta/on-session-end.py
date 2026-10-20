#!/usr/bin/env python3
"""Hook: on-session-end — close out the session row on Stop event.

The learning-loop analyzers (friction harvest, gap classification, workflow patterns,
retroactive validation) are NOT run here. Claude Code waits for a Stop hook, and the
pattern analyzer scans every row of the events table -- measured past three minutes on
a 1.5 GB database -- so running it inline hung the end of every turn. This hook now
closes the session row (milliseconds), records the session as pending analysis, and
starts a detached worker (``--analyze``) that this process does not wait for.

The worker is one process at a time (a lock), drains every pending session in one pass,
and CLAIMS each session before analysing it, so a worker that is killed mid-scan leaves
nothing behind that makes the next turn start the same scan again.
"""

import contextlib
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path


def _get_plugin_root() -> Path:
    sidecar = Path(__file__).resolve()
    for _ in range(8):
        candidate = sidecar / ".plugin-root"
        if candidate.is_file():
            try:
                return Path(candidate.read_text(encoding="utf-8").strip()).resolve()
            except Exception:
                pass
        sidecar = sidecar.parent
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[4]


_PLUGIN_ROOT = _get_plugin_root()
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))
if str(_PLUGIN_ROOT / "hooks") not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))

from core.config import paths  # noqa: E402
from core.event_store.studio_db import (  # noqa: E402
    end_session,
    has_sentinel,
    run_session_end_analyzers,
    set_sentinel,
)


def _int_env(name: str, default: int) -> int:
    """An integer from the environment. A malformed value ("6h") is the default, not an
    ImportError: this runs at import, before the hook has closed the session row."""
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


#: A lock whose heartbeat is older than this belongs to a worker that died. It is age, not
#: a pid probe: ``os.kill(pid, 0)`` TERMINATES the process on Windows, so there is no safe
#: liveness check to make. A live worker beats every _HEARTBEAT_S from a thread, so the
#: lock stays fresh however long one scan runs, and a hard-killed worker (taskkill, a
#: reboot, a job-object kill) stops blocking analysis after ten minutes, not hours.
_LOCK_STALE_S = 600
_HEARTBEAT_S = 30
#: The pattern scan is global, not per-session, and its result barely moves between two
#: sessions an hour apart. Running it for every session is what made it a per-turn cost.
_PATTERN_MIN_INTERVAL_S = _int_env("DS_PATTERN_ANALYSIS_MIN_INTERVAL_S", 6 * 3600)
#: Passes the worker makes after releasing its lock, to catch a session enqueued in the
#: gap between its last empty read and the release (that session's own spawn saw the
#: lock held and exited).
_DRAIN_PASSES = 3


def _state() -> Path:
    return paths.state_dir()


def _pending_dir() -> Path:
    return _state() / "session-analysis-pending"


def _lock_path() -> Path:
    return _state() / "session-analyzers.lock"


def _enqueue(session_id: str) -> None:
    """Record *session_id* as awaiting analysis. The file's name is a hash so any id is
    a safe filename; its content is the id."""
    pending = _pending_dir()
    pending.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha1(session_id.encode("utf-8")).hexdigest()[:16]
    (pending / name).write_text(session_id, encoding="utf-8")


def _has_pending() -> bool:
    pending = _pending_dir()
    return pending.is_dir() and any(pending.iterdir())


def _claim_pending() -> list[str]:
    """Take every pending session. Each file is deleted as it is read: after this the
    session is the caller's, and a crash does not put it back."""
    pending = _pending_dir()
    if not pending.is_dir():
        return []
    claimed: list[str] = []
    for entry in sorted(pending.iterdir()):
        try:
            session_id = entry.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue  # another worker claimed it between the listing and the read
        except (OSError, ValueError):
            # Unreadable, or not UTF-8. It sorts first and would be re-read, and fail,
            # on every run, so no session behind it would ever be analysed: drop it.
            entry.unlink(missing_ok=True)
            continue
        try:
            entry.unlink()
        except FileNotFoundError:
            continue  # claimed by another worker after we read it: it is theirs
        if session_id:
            claimed.append(session_id)
    return claimed


def _claim_pattern_slot() -> bool:
    """True if the global scan is due. Stamps the slot BEFORE the scan so a scan that
    is killed is not retried until the interval passes, not at the next opportunity."""
    marker = _state() / "pattern-analysis.last"
    if marker.exists() and time.time() - marker.stat().st_mtime < _PATTERN_MIN_INTERVAL_S:
        return False
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    return True


def _acquire_lock() -> bool:
    lock = _lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime < _LOCK_STALE_S:
                    return False
                # A dead worker's lock. The rename is atomic, so of two workers that both
                # see it stale only one takes it; the other finds it gone and retries.
                stolen = lock.with_name(f"{lock.name}.stolen.{os.getpid()}")
                os.replace(lock, stolen)
                stolen.unlink()
            except FileNotFoundError:
                continue  # the holder finished, or another worker won the steal: retry
            continue
        with os.fdopen(fd, "w") as handle:
            handle.write(str(os.getpid()))
        return True
    return False


def _note(message: str) -> None:
    """Say what went wrong, in the diagnostics log. A hook may not raise, but it also may
    not fail without a trace: a worker that died silently is how the old design hid a
    three-minute scan. This is the one place a log write is allowed to fail quietly."""
    diag = paths.home_dir() / "diagnostics" / "session-analyzers.log"
    with contextlib.suppress(OSError):
        diag.parent.mkdir(parents=True, exist_ok=True)
        with diag.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.time()}: {message}" + chr(10))


def _record_run(session_ids: list[str], pattern: bool, started: float, error: str | None) -> None:
    """The worker's cost, in the same timing log every other handler reports to, so it
    shows up in `ds analytics` instead of nowhere. A failure also goes to diagnostics."""
    from control.execution.dispatch_helpers import write_timing

    elapsed_ms = (time.monotonic() - started) * 1000
    write_timing(_state(), "SessionAnalysis", "run_session_end_analyzers", elapsed_ms)
    if error is not None:
        _note(f"sessions={len(session_ids)} pattern={pattern} after {elapsed_ms:.0f} ms: {error}")


def _drain() -> None:
    """One worker's pass: take every pending session until none is left."""
    while True:
        session_ids = _claim_pending()
        if not session_ids:
            return
        pattern = _claim_pattern_slot()
        started = time.monotonic()
        error: str | None = None
        try:
            run_session_end_analyzers(session_ids, pattern_analysis=pattern)
        except BaseException as exc:  # noqa: BLE001 -- a worker records a failure, it does not die
            error = repr(exc)
        _record_run(session_ids, pattern, started, error)


def _beat(stop: threading.Event) -> None:
    """Keep the lock fresh while the worker lives, however long one scan runs. A daemon
    thread, so a killed worker stops beating and its lock goes stale."""
    while not stop.wait(_HEARTBEAT_S):
        with contextlib.suppress(OSError):
            os.utime(_lock_path())


def run_worker() -> int:
    """The detached worker: drain pending sessions, one process at a time."""
    try:
        for _ in range(_DRAIN_PASSES):
            if not _acquire_lock():
                return 0  # the holder drains our session too: it re-reads until empty
            stop = threading.Event()
            threading.Thread(target=_beat, args=(stop,), daemon=True).start()
            try:
                _drain()
            finally:
                stop.set()
                _lock_path().unlink(missing_ok=True)
            if not _has_pending():
                break
    except Exception as exc:
        _note(f"worker failed: {exc!r}")
        return 1
    return 0


def _analysis_enabled() -> bool:
    """DS_SESSION_ANALYSIS=0 turns the whole hand-off off: with only the spawn disabled,
    sessions were still queued and nothing ever drained them."""
    return os.environ.get("DS_SESSION_ANALYSIS") != "0"


def _spawn_worker() -> None:
    """Start ``--analyze`` fully detached. Nothing here waits for it, and nothing it
    holds can keep Claude Code waiting: all three std handles are redirected, so no
    pipe is inherited and the hook's stdout reaches EOF when this process exits."""
    cmd = [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--analyze"]
    # The worker needs the same importable code this process has; -I would drop it.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
        "env": env,
    }
    if os.name == "nt":
        flags = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )
        breakaway = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
        try:
            # Out of the hook's job object, which Claude Code may kill with the hook.
            subprocess.Popen(cmd, creationflags=flags | breakaway, **kwargs)
        except OSError:
            # A job that forbids breakaway refuses the flag; detached is still correct.
            subprocess.Popen(cmd, creationflags=flags, **kwargs)
    else:
        subprocess.Popen(cmd, start_new_session=True, **kwargs)


def main() -> None:
    try:
        payload = json.loads(raw) if (raw := sys.stdin.read()).strip() else {}
    except Exception:
        payload = {}

    if not (session_id := payload.get("session_id", "")):
        return

    sentinel_key = f"session-ended-{session_id}"
    if has_sentinel(sentinel_key):
        return

    input_tokens = payload.get("prompt_tokens") if "prompt_tokens" in payload else None
    output_tokens = payload.get("completion_tokens") if "completion_tokens" in payload else None
    outcome = payload.get("stop_reason") or "end_turn"

    closed = False
    try:
        closed = bool(
            end_session(
                session_id, outcome=outcome, input_tokens=input_tokens, output_tokens=output_tokens
            )
        )
    except Exception:
        pass

    # validate_session_research removed — raw_research dropped migration 131

    try:
        set_sentinel(sentinel_key, "session")
    except Exception:
        pass

    if closed and _analysis_enabled():
        try:
            _enqueue(session_id)
            _spawn_worker()
        except Exception as exc:
            _note(f"could not hand session {session_id} to the analyzer worker: {exc!r}")


if __name__ == "__main__":
    try:
        if "--analyze" in sys.argv[1:]:
            sys.exit(run_worker())
        main()
    except Exception:
        pass
