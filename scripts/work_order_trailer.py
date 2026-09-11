"""Append the `Work-Order:` trailer a commit's own changed files imply.

WO 654a54d7. The trailer is the documented way a commit stays discoverable to the work
order it belongs to, and nothing asked for one -- it was remembered AFTER a verdict failed,
when adding it meant rewriting history. This repo did exactly that on 2026-09-11: four
commits were rebuilt to carry trailers, and the run that motivated it then showed the
trailer had not even been the operative locator.

It is derivable rather than remembered. `in_progress_work_order` already computes which
open work order's declared module boundary covers a path -- the on-edit enforcement hook
uses that same call to decide whether an edit is allowed at all -- so the commit-msg stage
can ask the same question of the staged files and write the answer down.

ADVISORY BY CONSTRUCTION. This never blocks a commit and never overwrites an author's
trailer. A commit whose files match no open boundary, or match several, is left alone:
guessing an attribution would be worse than omitting one, which is the rule
`in_progress_work_order` already applies when two work orders both claim a path.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def staged_files(repo_root: Path) -> list[str]:
    """Paths staged for this commit, relative to the repo root."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except Exception:  # noqa: BLE001 - a trailer is never worth failing a commit over
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def trailer_for(paths: list[str], repo_root: Path) -> str | None:
    """The single work order every declared-boundary match agrees on, or None.

    None when nothing matches, when the match rests on recency rather than a declared
    boundary, or when the staged files point at different work orders. The last case is
    the one worth naming: a commit spanning two work orders has no single correct trailer,
    and writing either would make the wrong one look responsible for the other's diff.
    """
    try:
        from runtime.lib.enforcement import in_progress_work_order, match_registered_project
    except Exception:  # noqa: BLE001
        return None

    claims: set[str] = set()
    for rel in paths:
        absolute = str(repo_root / rel)
        try:
            # The project is resolved from the PATH, the same call the on-edit hook makes,
            # rather than from a config value -- a second way of deciding which project a
            # file belongs to would be a second answer to a question already answered.
            project = match_registered_project(absolute)
            if not project:
                continue
            wo = in_progress_work_order(
                project["project_id"],
                file_path=absolute,
                project_path=project["project_path"],
            )
        except Exception:  # noqa: BLE001
            return None
        if not wo:
            continue
        # Only a DECLARED boundary attributes a commit. `most_recently_started` is the
        # recency guess the boundary rule exists to replace.
        if wo.get("attribution") != "module_boundary":
            continue
        claims.update(wo.get("claimants") or [wo["work_order_id"]])
    if len(claims) != 1:
        return None
    return f"Work-Order: {claims.pop()}"


def apply(msg_path: Path, repo_root: Path = REPO_ROOT) -> bool:
    """Append the trailer to the commit message file. True when one was added."""
    try:
        message = msg_path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return False
    if "Work-Order:" in message:
        return False
    trailer = trailer_for(staged_files(repo_root), repo_root)
    if not trailer:
        return False
    body = message.rstrip("\n")
    msg_path.write_text(f"{body}\n\n{trailer}\n", encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return 0
    apply(Path(args[0]))
    return 0  # never blocks


if __name__ == "__main__":
    raise SystemExit(main())
