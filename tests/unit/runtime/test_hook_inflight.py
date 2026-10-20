"""A hook handler that hangs or is killed must be visible.

hook-timing.jsonl is written when a handler RETURNS, so a hung handler is absent from it
by construction: on-session-end read 4 to 14 ms in the log while it held the end of every
turn for minutes. dispatch_helpers.inflight() leaves a marker for exactly as long as a
handler runs; ds analytics lists what is left.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from control.execution import dispatch_helpers, dispatch_tracking
from control.execution.dispatch_helpers import inflight, inflight_dir

REPO = Path(__file__).resolve().parents[3]

#: A handler body that reports which markers existed WHILE it ran.
_PROBE = (
    "import sys\n"
    "def main():\n"
    "    from pathlib import Path\n"
    "    d = Path({marker_dir!r})\n"
    "    sys.modules['probe_seen'] = [p.name for p in d.glob('*.json')]\n"
)


def _markers(state: Path) -> list[Path]:
    return sorted(inflight_dir(state).glob("*.json")) if inflight_dir(state).is_dir() else []


def _harvester(monkeypatch, state: Path):
    sys.path.insert(0, str(REPO / "interfaces" / "cli"))
    try:
        from ds_analytics import harvester
    finally:
        sys.path.pop(0)
    monkeypatch.setattr(harvester.paths, "state_dir", lambda: state)
    return harvester


def test_marker_exists_exactly_while_the_handler_runs(tmp_path):
    with inflight(tmp_path, "Stop", "on-session-end"):
        (marker,) = _markers(tmp_path)
        record = json.loads(marker.read_text(encoding="utf-8"))
        assert record["handler"] == "on-session-end"
        assert record["event"] == "Stop"
        assert record["pid"] == os.getpid()
    assert _markers(tmp_path) == []


def test_a_handler_that_raises_is_not_a_hang(tmp_path):
    with pytest.raises(RuntimeError):
        with inflight(tmp_path, "Stop", "boom"):
            raise RuntimeError("handler failed")
    assert _markers(tmp_path) == [], "an exception is a failure, which is already recorded"


def test_a_killed_process_leaves_its_marker(tmp_path):
    """The case the timing log cannot see: the process dies inside the handler."""
    code = (
        "import os, sys\n"
        f"sys.path.insert(0, {str(REPO)!r})\n"
        "from pathlib import Path\n"
        "from control.execution.dispatch_helpers import inflight\n"
        f"with inflight(Path({str(tmp_path)!r}), 'Stop', 'on-session-end'):\n"
        "    os._exit(1)\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert done.returncode == 1, done.stderr
    assert [m.name.split("-", 1)[1] for m in _markers(tmp_path)] == ["on-session-end.json"]


def test_marking_never_breaks_the_handler(tmp_path):
    """A state dir that cannot be written to must cost the hook nothing."""
    blocker = tmp_path / "state"
    blocker.write_text("a file where the directory should be", encoding="utf-8")
    ran: list[int] = []
    with inflight(blocker, "Stop", "x"):
        ran.append(1)
    assert ran == [1]


def test_markers_older_than_the_retention_window_are_pruned(tmp_path):
    directory = inflight_dir(tmp_path)
    directory.mkdir(parents=True)
    old = directory / "1-ancient.json"
    old.write_text("{}", encoding="utf-8")
    long_ago = time.time() - dispatch_helpers.INFLIGHT_MAX_AGE_S - 60
    os.utime(old, (long_ago, long_ago))
    with inflight(tmp_path, "Stop", "fresh"):
        assert not old.exists()


# --- both dispatchers use it --------------------------------------------------------


def test_run_handlers_marks_each_handler_while_it_runs(tmp_path, monkeypatch):
    state = tmp_path / "state"
    handler = tmp_path / "probe.py"
    handler.write_text(_PROBE.format(marker_dir=str(inflight_dir(state))), encoding="utf-8")
    monkeypatch.setattr(dispatch_tracking, "_log_hook_execution", lambda **kw: None)

    dispatch_tracking.run_handlers([("on-probe", handler)], "{}", "Stop", state)

    seen = sys.modules.pop("probe_seen")
    assert len(seen) == 1 and seen[0].endswith("-on-probe.json"), seen
    assert _markers(state) == [], "the marker outlived the handler"


def test_on_stop_dispatch_marks_each_stop_handler(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location(
        "on_stop_dispatch_under_test", REPO / "runtime" / "hooks" / "meta" / "on-stop-dispatch.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    state = tmp_path / "state"
    handler = tmp_path / "probe.py"
    handler.write_text(_PROBE.format(marker_dir=str(inflight_dir(state))), encoding="utf-8")
    monkeypatch.setattr(mod, "STATE_DIR", state)
    monkeypatch.setattr(mod, "_dispatch_handoff_continuation", lambda: None)
    monkeypatch.setattr(mod, "HANDLERS", [("on-probe", handler)])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

    mod.main()

    seen = sys.modules.pop("probe_seen")
    assert len(seen) == 1 and seen[0].endswith("-on-probe.json"), seen
    assert _markers(state) == []


# --- ds analytics reports what never finished ---------------------------------------


def test_the_harvester_lists_a_stuck_handler_and_skips_a_running_one(tmp_path, monkeypatch):
    harvester = _harvester(monkeypatch, tmp_path)
    directory = inflight_dir(tmp_path)
    directory.mkdir(parents=True)
    now = time.time()
    for name, age in (("stuck", 3600), ("running-now", 5)):
        (directory / f"1-{name}.json").write_text(
            json.dumps(
                {
                    "pid": 1,
                    "event": "Stop",
                    "handler": name,
                    "started_epoch": now - age,
                    "started_at": "2026-10-19T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
    (directory / "2-garbage.json").write_text("{not json", encoding="utf-8")

    found = harvester.harvest_unfinished_handlers(now=now)

    assert [f["handler"] for f in found] == ["stuck"]
    assert found[0]["age_s"] == 3600


def test_harvest_hook_timing_carries_the_unfinished_list_even_with_no_timing_log(
    tmp_path, monkeypatch
):
    harvester = _harvester(monkeypatch, tmp_path)
    assert harvester.harvest_hook_timing()["unfinished"] == []


def test_the_marker_is_written_even_when_cleanup_races_another_process(tmp_path, monkeypatch):
    """Cleanup shared a suppress block with the write. A marker deleted by another process
    between the glob and the stat raised FileNotFoundError and skipped THIS handler's
    marker, so a hang there would have left no trace. Measured at 4% to 34% of runs."""
    directory = inflight_dir(tmp_path)
    directory.mkdir(parents=True)
    ghost = directory / "9-ghost.json"
    ghost.write_text("{}", encoding="utf-8")
    real_stat = Path.stat

    def _stat(self, *args, **kwargs):
        if self == ghost:
            raise FileNotFoundError(2, "vanished", str(self))  # a peer just finished
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _stat)

    with inflight(tmp_path, "Stop", "racer"):
        names = sorted(m.name for m in directory.glob("*.json"))

    assert any(n.endswith("-racer.json") for n in names), names
