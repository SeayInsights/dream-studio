"""``ds review`` — convene the review round table from the CLI.

WHY THIS EXISTS. `core/gates/round_table.py` has carried a full argument surface for a
while — `--repo-root`, `--seat`, `--lane`, `--all`, `--json` — reachable only as
`py -m core.gates.round_table`. A capability the `ds` CLI does not expose is one an
operator has to already know the module path for, and every skill that wants it has to
name an internal module rather than a command. This is that door; it adds no review
logic and owns no verdict.

WHAT `--pr` ADDS, AND WHY IT IS NOT A NEW MECHANISM. `convene()` already accepts an
explicit `paths` list, so reviewing a pull request is a question of *which* paths, not of
new machinery: `gh pr diff <n> --name-only` is the change set, handed to the same
function the local path uses. The table is identical; only the file list differs.

**A `--pr` THAT CANNOT READ THE PR FAILS, IT DOES NOT FALL BACK.** `changed_paths()`
returns `[]` to mean "git could not tell", and the caller treats that as a reason to
convene EVERYTHING rather than nothing — the right default, because over-reviewing is
safe and under-reviewing reports a clean review of a tree nobody looked at. That default
is wrong here. An operator who typed `--pr 812` is asking about one specific change set,
and convening the whole bench over their local working tree while printing a report they
will read as "PR 812 reviewed" is the substitution this module exists to refuse. So a
`gh` that is missing, unauthenticated, or pointed at an unknown PR exits non-zero and
says which.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

GH_TIMEOUT_SECONDS = 60


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach the ``review`` subparser."""
    review_cmd = subcommands.add_parser(
        "review", help="Convene the review round table over a change set"
    )
    review_cmd.add_argument(
        "--repo",
        default=None,
        help=(
            "Convene against THIS project instead of the one ds lives in. That project's"
            " own canonical/review_lanes.yml is read, so it is asked its own questions."
        ),
    )
    review_cmd.add_argument(
        "--pr",
        default=None,
        metavar="N",
        help=(
            "Convene over the files a GitHub pull request touches, read via `gh pr diff"
            " --name-only`. Fails if the PR cannot be read; it never falls back to the"
            " local tree, because a report headed by a PR number must be about that PR."
        ),
    )
    review_cmd.add_argument(
        "--seat",
        default=None,
        help="Convene one seat alone (exact name). An unknown seat fails, naming the set.",
    )
    review_cmd.add_argument(
        "--lane",
        dest="lane_id",
        default=None,
        help="Convene one lane alone (exact id). An unknown lane fails, naming the set.",
    )
    review_cmd.add_argument(
        "--all",
        dest="all_seats",
        action="store_true",
        help=(
            "Convene every seat regardless of relevance to the change set. Relevance is"
            " an inference about a diff; an operator asking for the whole bench is not"
            " making one."
        ),
    )
    review_cmd.add_argument(
        "--no-detectors",
        action="store_true",
        help="List the lanes without running the detectors (fast, and answers nothing).",
    )
    review_cmd.add_argument(
        "--json", action="store_true", help="Emit the report as JSON instead of a table."
    )


def pr_changed_paths(pr: str, *, repo_root: Path | None = None) -> list[str]:
    """The files a pull request touches.

    Raises ``RuntimeError`` rather than returning an empty list. An empty list is how
    `changed_paths` says "I could not tell", and its caller reads that as a reason to
    convene the whole bench -- correct there, and a misreport here, where the operator
    named one pull request and will read the output as being about it.
    """
    try:
        proc = subprocess.run(
            ["gh", "pr", "diff", str(pr), "--name-only"],
            cwd=str(repo_root) if repo_root else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:  # gh not installed
        raise RuntimeError(
            "`gh` is not on PATH, so --pr cannot read the pull request. Install the GitHub"
            " CLI, or convene over a local change set without --pr."
        ) from exc
    except subprocess.SubprocessError as exc:
        raise RuntimeError(f"`gh pr diff {pr}` could not be run: {exc}") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        raise RuntimeError(f"`gh pr diff {pr}` failed: {detail[-1] if detail else 'no error text'}")

    paths = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    if not paths:
        raise RuntimeError(
            f"PR {pr} reports no changed files. Refusing to convene, because an empty"
            " change set here would silently become a review of everything."
        )
    return paths


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Dispatch ``ds review``. Exit codes mirror the round table's own CLI."""
    from core.gates.round_table import _render, convene

    repo_root = Path(args.repo) if args.repo else None

    paths: list[str] | None = None
    if args.pr:
        try:
            paths = pr_changed_paths(args.pr, repo_root=repo_root)
        except RuntimeError as exc:
            print(f"ds review: {exc}", file=sys.stderr)
            return 2

    try:
        report = convene(
            run_detectors=not args.no_detectors,
            repo_root=repo_root,
            seat=args.seat,
            lane_id=args.lane_id,
            all_seats=args.all_seats,
            paths=paths,
        )
    except (KeyError, FileNotFoundError) as exc:
        # NAMED, NOT SWALLOWED. A typo that convened nothing would print an empty table
        # and exit 0 -- a clean review of everything.
        print(f"ds review: {exc}".replace('"', ""), file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2, sort_keys=True) if args.json else _render(report))
    # "unchecked" is a deliberate listing, not a failure -- but it is not a pass either.
    return 1 if report["status"] == "fail" else 0
