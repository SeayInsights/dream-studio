#!/usr/bin/env python3
"""Append-only hook entry point. Records an event and exits. Nothing else.

THIS FILE MUST NOT IMPORT DREAM STUDIO. That is its entire reason to exist.

Measured 2026-09-21 on the operator's machine:

    bare interpreter start .................  33 ms
    this script ............................  55 ms
    importing the DS core ..................  229 ms
    the full dispatcher ....................  283 ms

Every hook used to take the last row. 69% of that was cold-loading pydantic,
jsonschema and the event store so a telemetry record could be written -- work
the hook does not need and the user waits for. PostToolUse fires on every tool
call (92,315 runs in one timing log), so that import bill was paid tens of
times per turn.

The split that makes this safe: a hook whose stdout is CONSUMED has to run
synchronously -- UserPromptSubmit injects context, the enforcers return a
verdict. A hook that only RECORDS does not. Those are the ones routed here.

Anything expensive happens later, in `drain()` (see hookq.py), on a process
that was going to pay the import cost anyway.

Keep the import list below empty of anything outside the standard library. A
convenience import here costs 200 ms on every tool call you make, forever.
"""

from __future__ import annotations

import json
import os
import sys
import time

_MAX_PAYLOAD = 64 * 1024


def _queue_path() -> str:
    """Resolve the queue file without importing core.config.paths.

    paths.user_data_dir() is the authority for this location, but importing it
    pulls the very dependency chain this script exists to avoid. The rule is
    duplicated here deliberately, and test_hook_queue.py pins the two in sync.
    """
    home = os.environ.get("DS_HOME") or os.path.join(os.path.expanduser("~"), ".dream-studio")
    return os.path.join(home, "state", "hookq.jsonl")


def main() -> int:
    try:
        # READ BYTES, NOT TEXT. sys.stdin.read() applies universal-newline
        # translation and decodes with the console codepage, so on Windows a
        # payload containing \r\n arrived as \n and anything outside cp1252 was
        # mangled -- silently, and only in the Python writer. The native
        # enqueuer reads raw bytes, so the two disagreed about what the hook
        # even said. test_hook_queue.py compares them on exactly these inputs.
        raw = sys.stdin.buffer.read(_MAX_PAYLOAD).decode("utf-8", "replace")
    except Exception:
        raw = ""

    record = {
        "event": sys.argv[1] if len(sys.argv) > 1 else "",
        "ts": time.time(),
        "payload": raw,
    }

    try:
        path = _queue_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # ONE write() of ONE line. Concurrent hook processes append to this file
        # with no lock between them; a single sub-4KB write to a file opened for
        # append is what keeps their lines from interleaving. Do not build the
        # line up with several writes, and do not switch to print().
        line = json.dumps(record, separators=(",", ":")) + "\n"
        # newline="" DISABLES Windows text-mode translation. Without it Python
        # writes \r\n while the native enqueuer writes \n, so one queue file ends
        # up with two framings -- caught 2026-09-21 when a byte-level read of a
        # file both had written hit a stray \r and refused to parse. Text-mode
        # reads paper over it; anything reading bytes does not.
        with open(path, "a", encoding="utf-8", newline="") as fh:
            fh.write(line)
    except Exception:
        # A hook may never break the tool call it observes. A dropped telemetry
        # record costs a row in a chart; a raised exception costs the user's work.
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
