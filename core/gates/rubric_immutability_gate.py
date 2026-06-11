"""Pre-push gate: block eval-rubric.yml changes without [rubric-update] commit token.

Exit 0: no rubric change in the push, OR rubric change with [rubric-update] in commit messages.
Exit 1: rubric change detected and no commit message carries [rubric-update].

Writes to guardrail_decisions with reason=rubric-immutability-constraint for audit.
"""

from __future__ import annotations

import subprocess
import sys
import time
import uuid
from pathlib import Path

RUBRIC_PATH = "canonical/skills/domains/eval-rubric.yml"
REQUIRED_TOKEN = "[rubric-update]"


def _changed_files() -> list[str]:
    """Return files changed between origin/main and HEAD."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def _commit_messages() -> str:
    """Return all commit messages between origin/main and HEAD."""
    result = subprocess.run(
        ["git", "log", "--format=%B", "origin/main...HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout


def _record_decision(action: str) -> None:
    """Write to guardrail_decisions for audit. Non-fatal on any error."""
    try:
        import sqlite3

        db_path = Path.home() / ".dream-studio" / "state" / "studio.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT OR IGNORE INTO guardrail_decisions"
            " (decision_id, rule_id, event_id, action, message, evaluated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                "rubric-immutability-constraint",
                None,
                action,
                (
                    "eval-rubric.yml change blocked — [rubric-update] token required"
                    if action == "block"
                    else "eval-rubric.yml change allowed — [rubric-update] token present"
                ),
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def main() -> int:
    changed = _changed_files()
    if RUBRIC_PATH not in changed:
        return 0

    messages = _commit_messages()
    if REQUIRED_TOKEN in messages:
        _record_decision("allow")
        print(f"[PASS] rubric-immutability: {RUBRIC_PATH} changed with {REQUIRED_TOKEN!r} token")
        return 0

    _record_decision("block")
    print(
        f"[FAIL] rubric-immutability: {RUBRIC_PATH} modified without {REQUIRED_TOKEN!r} in any commit message.",
        file=sys.stderr,
    )
    print(
        f"       Add {REQUIRED_TOKEN!r} to your commit message to authorize this rubric change.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
