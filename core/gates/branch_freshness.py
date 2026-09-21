"""How far behind its base is this branch, and does the reviewer know?

THE LANE `a-branch-behind-its-base` DECLARED THIS DETECTOR AND NOBODY WROTE IT.
The registry gate refuses a lane whose detector does not import, but that gate was
never wired into pre-push, so the claim stood unchecked: the lane read as
mechanically enforced while `py -m core.gates.branch_freshness` was a
ModuleNotFoundError.

THE DEFECT IT WATCHES FOR. A pull request trial-merges clean while being far
enough behind its base that the review read a tree nobody will ship. In the
precedent pass, #812 and #814 were 38 commits behind and #849 and #858 were 5
behind; all four trial-merged clean, and one was asked to sync explicitly. A
clean trial-merge is not currency -- it says the diffs do not textually collide,
not that the reviewed behaviour is the behaviour that lands.

CLAUDE.md already says "Never push to stale/old branches -- check branch
freshness first", enforced by nothing. This is the enforcement.

ADVISORY BY DESIGN. Being behind is sometimes correct: a revert off a tag, a
hotfix from a release point. Blocking it would be a wall, and a gate that walls
legitimate work is a gate that gets switched off. The lane's job is not that a
branch is never behind -- it is that nobody reviews a stale tree without knowing
by how much.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Behind by more than this and the review is reading a materially different tree.
#: 0 means any drift is reported, which is what the precedent argues for -- two of
#: its four cases were only 5 commits behind and both still mattered.
DEFAULT_THRESHOLD = 0


def _git(root: Path, *args: str) -> tuple[int, str]:
    """Run git and return (returncode, combined output).

    encoding is pinned because a subprocess with text=True and no encoding decodes
    with the platform locale codec -- cp1252 on Windows -- and one unmapped byte
    then hands the caller returncode 0 with stdout=None. The locale-decode gate
    exists for exactly this and this module is not exempt from it.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root),
            check=False,  # a non-zero git is an answer here, not an exception
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def run(root: Path | None = None, base_ref: str | None = None) -> dict:
    """Commits on the base that are not on HEAD.

    A COUNT THIS CANNOT DETERMINE IS NOT A COUNT OF ZERO. If git is absent, the
    base ref is unknown, or the repository has no origin, this reports `unknown`
    rather than `clean`. Reporting a tree it could not read as fresh is the
    compared-nothing-reported-clean shape the review lanes exist to refuse.
    """
    root = Path(root) if root else REPO_ROOT
    base = base_ref or os.environ.get("DREAM_STUDIO_BASE_REF", "origin/main")

    rc, head = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return {"status": "unknown", "reason": f"cannot read HEAD: {head}", "base": base}

    rc, out = _git(root, "rev-list", "--count", f"HEAD..{base}")
    if rc != 0:
        return {
            "status": "unknown",
            "reason": f"cannot count commits against {base}: {out}",
            "base": base,
            "branch": head,
        }
    try:
        behind = int(out.split()[0])
    except (ValueError, IndexError):
        return {
            "status": "unknown",
            "reason": f"git returned an uncountable answer: {out!r}",
            "base": base,
            "branch": head,
        }

    rc, ahead_out = _git(root, "rev-list", "--count", f"{base}..HEAD")
    ahead = int(ahead_out.split()[0]) if rc == 0 and ahead_out.split() else None

    return {
        "status": "behind" if behind > DEFAULT_THRESHOLD else "current",
        "branch": head,
        "base": base,
        "behind": behind,
        "ahead": ahead,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report how far behind its base this branch is, so no review reads a stale tree unknowingly."
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help=(
            "Measure THIS tree instead of the one this gate lives in. The round table"
            " appends it when convening against another project; without it the gate"
            " reads its own checkout and reports that as the other project's result."
        ),
    )
    parser.add_argument(
        "--base",
        default=None,
        help="Base ref to measure against (default: DREAM_STUDIO_BASE_REF, else origin/main).",
    )
    args = parser.parse_args(argv)

    result = run(Path(args.repo_root) if args.repo_root else None, args.base)

    if result["status"] == "unknown":
        # NOT A FINDING AND NOT A PASS. Exit 0 so an environment without git or
        # without a fetched base does not manufacture a defect, but say plainly
        # that the question went unanswered rather than printing OK.
        print(f"branch-freshness: UNKNOWN - {result['reason']}")
        return 0

    if result["status"] == "behind":
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"\nbranch-freshness: {result['branch']} is {result['behind']} commit(s) behind"
            f" {result['base']}. A clean trial-merge does not mean the reviewed behaviour is"
            " the behaviour that lands. Sync, or say why being behind is deliberate.",
            file=sys.stderr,
        )
        return 1

    print(f"branch-freshness: OK - {result['branch']} is current with {result['base']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
