#!/usr/bin/env python3
"""Switch PostToolUse from the inline dispatcher to the append-only enqueuer.

Run once, by the operator:

    py scripts/apply_append_only_hooks.py --dry-run     # show the change
    py scripts/apply_append_only_hooks.py               # apply it

Why this is not part of `ds setup`
----------------------------------
`step_settings_merge` ADDS hooks that are missing; it has no concept of one
hook superseding another. The enqueuer and the dispatcher have different
identities on purpose -- they are different programs -- so a merge would
install the fast hook BESIDE the slow one and PostToolUse would run both.
That is worse than doing nothing, which is exactly why this is a separate,
explicit, reversible step rather than something an install does quietly.

What changes
------------
PostToolUse stops running the dispatcher inline (267 ms per tool call, 196 ms
of it spent importing pydantic/jsonschema/event_store to append one row) and
instead appends a line and exits: 51 ms with enqueue.py, 27 ms with the
compiled ds-enqueue. The handlers still run -- `hookq.drain()` replays them on
UserPromptSubmit and Stop, which are synchronous anyway and have already paid
the import cost.

Nothing is lost. The queue is on disk, drain is at-least-once, and
core.config.retention has a budget for orphaned queue files.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from interfaces.cli.setup_hooks import (  # noqa: E402
    SETTINGS_JSON,
    hook_identity,
    resolve_hook_command,
)

HOOKS_JSON = REPO / "hooks" / "hooks.json"


def _enqueue_command() -> str | None:
    """The PostToolUse enqueue command, already resolved for this machine."""
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    for group in data.get("hooks", {}).get("PostToolUse", []):
        for hook in group.get("hooks", []):
            if "enqueue.py" in hook.get("command", ""):
                return resolve_hook_command(hook["command"])
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print the change, write nothing")
    ap.add_argument("--revert", action="store_true", help="put the inline dispatcher back")
    args = ap.parse_args()

    enqueue = _enqueue_command()
    if enqueue is None:
        print("hooks.json has no PostToolUse enqueue command; nothing to apply.")
        return 1

    settings = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))

    # The status line is gone. It spawned a Python process per render and shelled
    # out to git four times inside each one -- 159 ms x ~30 renders, about 4.8
    # seconds a turn. Leaving the settings entry behind after deleting the script
    # would spawn a process per render that can only fail, so it goes too.
    dropped_statusline = settings.pop("statusLine", None) is not None

    groups = settings.get("hooks", {}).get("PostToolUse", [])
    if not groups:
        print("settings.json registers no PostToolUse hooks; nothing to apply.")
        return 1

    target = hook_identity(enqueue)
    changed: list[tuple[str, str]] = []

    for group in groups:
        for hook in group.get("hooks", []):
            cmd = hook.get("command", "")
            ident = hook_identity(cmd)
            if args.revert:
                if ident == target:
                    print("  revert is not automatic: restore from a settings.json.bak-* copy.")
                    return 1
                continue
            # The inline dispatcher on PostToolUse is what the enqueuer replaces.
            # run.py (the emitter) is left alone -- different hook, different job.
            if ident.startswith("hooks.py:") and ident.endswith(":PostToolUse"):
                changed.append((cmd, enqueue))
                if not args.dry_run:
                    hook["command"] = enqueue

    if not changed and not dropped_statusline:
        already = any(
            hook_identity(h.get("command", "")) == target
            for g in groups
            for h in g.get("hooks", [])
        )
        print("Already applied." if already else "No inline PostToolUse dispatcher found.")
        return 0

    if dropped_statusline:
        print("  - statusLine entry removed (the script itself is already deleted)\n")

    for before, after in changed:
        print(f"  - {before[-72:]}\n  + {after[-72:]}\n")

    if args.dry_run:
        print(f"DRY RUN: {len(changed)} hook(s) + statusLine would change. Re-run to apply.")
        return 0

    backup = SETTINGS_JSON.with_suffix(f".json.bak-appendonly-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(SETTINGS_JSON, backup)
    SETTINGS_JSON.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    print(f"Applied {len(changed)} hook(s). Backup: {backup.name}")
    print("Restart Claude Code for the change to take effect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
