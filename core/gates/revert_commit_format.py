"""Conventional-revert guard — reject GitHub-UI ``Revert "..."`` commit subjects.

The GitHub "Revert" button writes ``Revert "<original subject>"``, which is not a
conventional commit: release-please cannot pair it with the original, so the reverted
feature lingers in the generated changelog as if it shipped. Reverts must use the
conventional ``revert(scope): ...`` (or ``revert: ...``) form instead.

Invoked by the pre-push gate over the commits in origin/main..HEAD; also runnable
standalone. Exit 0 = clean, 1 = a GitHub-UI revert subject was found.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# GitHub-UI reverts start with `Revert "` (or `Revert '`). Conventional reverts start
# with `revert:` / `revert(scope):` (lowercase, colon) and are allowed.
_GH_UI_REVERT = re.compile(r"""^Revert\s+["']""")


def check_revert_subject(subject: str) -> str | None:
    """Return a violation reason if ``subject`` is a GitHub-UI revert, else None."""
    first = subject.strip().splitlines()[0].strip() if subject.strip() else ""
    if _GH_UI_REVERT.match(first):
        return (
            f"GitHub-UI revert subject {first!r} — use conventional `revert(scope): ...` "
            f"(or `revert: ...`) so the revert pairs with the original and the changelog "
            f"stays honest"
        )
    return None


def _commit_subjects(base_ref: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "log", "--format=%s", f"{base_ref}..HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=REPO_ROOT,
            timeout=15,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    base_ref = os.environ.get("DREAM_STUDIO_BASE_REF", "origin/main")
    violations = [
        (subject, reason)
        for subject in _commit_subjects(base_ref)
        if (reason := check_revert_subject(subject))
    ]
    if not violations:
        return 0
    print("REVERT FORMAT: GitHub-UI revert commit(s) found — rewrite as conventional reverts")
    for _subject, reason in violations:
        print(f"  {reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
