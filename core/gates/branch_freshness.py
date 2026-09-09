"""Gate: say how far behind its base this branch is, before anyone reviews it.

REVIEW LANE ``a-branch-behind-its-base`` (canonical/review_lanes.yml).

THE FINDING THIS COMES FROM. The Surveyor, on the platform/gateway pass: plat#812 and #814
were 38 commits behind and gw#849 and #858 were 5 behind, and all four TRIAL-MERGED CLEAN.
The Herald asked #812 to sync explicitly. A clean trial-merge is not currency -- it says the
texts do not collide, not that the review read the tree that will ship. A reviewer who does
not know the distance cannot know which of the two they read.

ADVISORY, DELIBERATELY. A behind branch is often legitimate: a revert off a tag, a hotfix
from a release point, a long-lived spike. Blocking on distance would be a wall someone
switches off, and the lane's job is not to forbid the state -- it is that nobody reviews a
stale tree without being told. So this always exits 0 and prints the number.

THIS WAS PROSE UNTIL NOW. CLAUDE.md says "Never push to stale/old branches -- check branch
freshness first", enforced by nothing, which is the shape this whole registry exists to end.

FAIL OPEN, LOUDLY. No base ref, a detached HEAD, or a repo without the remote yields a
stated "could not measure" rather than a silent pass -- a check that could not run must not
read like a check that found nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Above this, the distance is worth a reviewer's attention. Chosen from the finding: the
#: two gateway PRs at 5 behind were called out alongside the platform pair at 38, so the
#: threshold that would have surfaced all four is low.
_NOTABLE_DISTANCE = 5


def _git(argv: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return proc.returncode, (proc.stdout or proc.stderr or "").strip()


def measure(base_ref: str | None = None) -> dict:
    """How far behind and ahead of its base this branch is.

    Public so a test can drive it against a real repository state rather than asserting on
    the shape of this module's source.
    """
    base = base_ref or os.environ.get("DREAM_STUDIO_BASE_REF") or "origin/main"

    code, head = _git(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if code != 0:
        return {"measured": False, "reason": f"could not read HEAD ({head})", "base": base}

    code, _ = _git(["git", "rev-parse", "--verify", base])
    if code != 0:
        return {
            "measured": False,
            "reason": f"base ref {base!r} does not resolve in this repository",
            "base": base,
            "branch": head,
        }

    code, counts = _git(["git", "rev-list", "--left-right", "--count", f"{base}...HEAD"])
    if code != 0 or len(counts.split()) != 2:
        return {
            "measured": False,
            "reason": f"could not count the distance ({counts})",
            "base": base,
            "branch": head,
        }
    behind, ahead = (int(part) for part in counts.split())
    return {
        "measured": True,
        "branch": head,
        "base": base,
        "behind": behind,
        "ahead": ahead,
        "notable": behind >= _NOTABLE_DISTANCE,
    }


def main() -> int:
    result = measure()
    if not result.get("measured"):
        # Stated, not silent: a check that could not run is not a check that passed.
        print(f"branch-freshness: UNMEASURED - {result.get('reason')}")
        return 0

    if result["branch"] == "main":
        print("branch-freshness: OK - on main; nothing to be behind.")
        return 0

    if result["notable"]:
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            f"branch-freshness: NOTE - {result['branch']} is {result['behind']} commit(s)"
            f" behind {result['base']} (and {result['ahead']} ahead). A clean trial-merge"
            " says the texts do not collide, not that a review read the tree that will"
            " ship: on the pass this lane came from, four PRs trial-merged clean at 5 and"
            " 38 behind. Advisory by design -- a behind branch is sometimes deliberate."
        )
        return 0

    print(
        f"branch-freshness: OK - {result['branch']} is {result['behind']} commit(s) behind"
        f" {result['base']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
