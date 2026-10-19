"""Helper functions for hook dispatchers (on-*-dispatch.py hooks)."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import re
import time
from collections.abc import Iterator
from pathlib import Path


def load_module(name: str, path: Path):
    """Dynamically load a Python module from file path."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_timing(state_dir: Path, event: str, handler: str, duration_ms: float) -> None:
    """Write hook timing record to hook-timing.jsonl."""
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "event": event,
            "handler": handler,
            "duration_ms": round(duration_ms, 2),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with (state_dir / "hook-timing.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


#: A marker this old is a record of something long dead, not a hang to investigate.
INFLIGHT_MAX_AGE_S = 7 * 86400


def inflight_dir(state_dir: Path) -> Path:
    return state_dir / "hook-inflight"


def _prune_stale_markers(directory: Path) -> None:
    """Drop markers older than the retention window. Each file is handled on its own: one
    that vanishes mid-scan (its handler just finished) must not abort the rest."""
    cutoff = time.time() - INFLIGHT_MAX_AGE_S
    candidates: list[Path] = []
    with contextlib.suppress(OSError):
        candidates = list(directory.glob("*.json"))
    for stale in candidates:
        with contextlib.suppress(OSError):
            if stale.stat().st_mtime < cutoff:
                stale.unlink(missing_ok=True)


@contextlib.contextmanager
def inflight(state_dir: Path, event: str, handler: str) -> Iterator[None]:
    """Mark *handler* as running for exactly as long as the ``with`` block.

    hook-timing.jsonl is written when a handler RETURNS, so a handler that hangs, or is
    killed by a timeout, never appears in it: the log showed ``on-session-end`` at 4 to
    14 ms while it was holding the end of every turn for minutes. A marker that exists
    only while the handler runs inverts that. Finishing -- or raising -- removes it; a
    hang or a kill leaves it behind, and ``ds analytics`` lists what is left.

    A marker is a file rather than a row in the timing log on purpose: extra rows would
    be counted by the harvester's per-handler averages. Nothing here may raise or block
    the hook, so every filesystem failure is skipped.
    """
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", handler)
    marker = inflight_dir(state_dir) / f"{os.getpid()}-{safe}.json"
    # THE MARKER IS WRITTEN FIRST, AND CLEANUP IS NOT ALLOWED TO PREVENT IT. Both used to
    # share one suppress(OSError) block: another process deleting its own marker between
    # the glob and the stat raised FileNotFoundError, the block exited, and this handler's
    # marker was never written -- measured at 4% to 34% of runs with a few processes at
    # once. A hang in such a handler would have left no trace, which is the one thing the
    # marker exists to prevent.
    with contextlib.suppress(OSError):
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "event": event,
                    "handler": handler,
                    "started_epoch": time.time(),
                    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            ),
            encoding="utf-8",
        )
    _prune_stale_markers(marker.parent)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            marker.unlink(missing_ok=True)
