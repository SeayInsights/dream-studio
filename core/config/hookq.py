"""The drain side of the append-only hook queue.

`runtime/hooks/enqueue.py` writes; this reads. The two halves never run in the
same process: enqueue is on the user's critical path and imports nothing,
drain runs on a process that was already paying the import cost.

Who drains, and why nobody had to build a daemon
------------------------------------------------
UserPromptSubmit and Stop are synchronous by necessity -- one injects context,
the other blocks on enforcement -- so they already import the DS core. They
fire about once per turn each. PostToolUse fires on every tool call: 92,315
runs against 19,787 prompts in the timing log, roughly 5x per turn and far more
on a heavy one.

So the expensive events are the rare ones and the cheap events are the frequent
ones. Draining from the rare synchronous events costs nothing extra and needs
no new process, no scheduler and no lifecycle to get wrong.

Crash safety
------------
Drain RENAMES the queue aside before reading it. A writer that is mid-append
during the rename keeps writing to its already-open handle, so at worst one
record lands in the rotated file after the drain started reading -- it is
picked up next time. A drainer that dies leaves the rotated file on disk and
the next drain recovers it. Nothing is read in place, so nothing is lost to a
truncate.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path

from core.config import paths

#: One drain must never become the new long pole. Anything beyond this waits for
#: the next one; the queue is already durable on disk.
MAX_RECORDS_PER_DRAIN = int(os.environ.get("DS_HOOKQ_MAX_DRAIN", "2000"))

#: Rotated-but-unprocessed files are recovered, but not forever -- a persistently
#: failing drain must not turn into a second unbounded store. It has a budget in
#: core.config.retention like everything else.
_ROTATED_GLOB = "hookq.*.jsonl"


def queue_path() -> Path:
    """The file enqueue.py appends to.

    enqueue.py cannot import this module (that would defeat it), so it derives
    the same path from DS_HOME independently. test_hook_queue.py asserts the two
    agree; if you move this, that test is what tells you.
    """
    return paths.state_dir() / "hookq.jsonl"


def pending_count() -> int:
    """Records waiting, without consuming them. For diagnostics and the guard."""
    total = 0
    for p in [queue_path(), *paths.state_dir().glob(_ROTATED_GLOB)]:
        try:
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                total += sum(1 for line in fh if line.strip())
        except OSError:
            continue
    return total


def _rotate() -> Path | None:
    """Move the live queue aside so it can be read without blocking writers."""
    live = queue_path()
    try:
        if not live.is_file() or live.stat().st_size == 0:
            return None
        rotated = live.with_name(f"hookq.{time.time_ns()}.jsonl")
        live.rename(rotated)
        return rotated
    except OSError:
        return None


def _read_records(path: Path) -> Iterator[dict]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    # A torn line means a writer died mid-write. One lost record
                    # is not worth abandoning the rest of the file.
                    continue
    except OSError:
        return


def drain(handler) -> int:
    """Feed every queued record to `handler(event_name, raw_payload)`.

    Returns the number processed. Never raises: this runs inside a hook, and a
    hook that raises breaks the user's turn.
    """
    processed = 0
    # Recover anything a previous drain rotated but did not finish, oldest first,
    # then take the current queue.
    try:
        rotated = sorted(paths.state_dir().glob(_ROTATED_GLOB))
    except OSError:
        rotated = []
    fresh = _rotate()
    if fresh is not None and fresh not in rotated:
        rotated.append(fresh)

    for path in rotated:
        # THE CAP IS CHECKED BETWEEN FILES, AND A FILE IS ALWAYS FINISHED.
        # Stopping mid-file and leaving it on disk re-delivered everything
        # already handled on the next drain -- the first version did exactly
        # that, and test_drain_is_capped_and_leaves_the_remainder caught it.
        # Whole-file semantics means the budget can overshoot by at most one
        # file, and nothing is ever processed twice.
        if processed >= MAX_RECORDS_PER_DRAIN:
            break
        for record in _read_records(path):
            try:
                handler(record.get("event", ""), record.get("payload", ""))
            except Exception:
                # One bad record must not strand the rest of the queue.
                pass
            processed += 1
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    return processed
