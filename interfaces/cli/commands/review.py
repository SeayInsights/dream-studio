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

    # ── the answers loop ────────────────────────────────────────────────────
    # A lane TESTS. Dispatch builds a container from the reviewed commit and records who
    # is asked what; a reviewer tests with --run; --record re-runs every reproduction it
    # is handed before storing it; --status says whether the review still holds the work
    # order.
    loop = review_cmd.add_mutually_exclusive_group()
    loop.add_argument(
        "--dispatch",
        action="store_true",
        help=(
            "Emit the outstanding lanes grouped by the reviewer that owns them, as JSON."
            " With --work-order it also builds the lane image from the reviewed commit"
            " (HEAD, or the PR head with --pr) and RECORDS the round; without it, it is a"
            " preview that records nothing. The chair's lanes have a null reviewer -- the"
            " caller is the chair."
        ),
    )
    loop.add_argument(
        "--run",
        metavar="COMMAND",
        default=None,
        help=(
            "Run COMMAND in --work-order's lane container (no network, no host state) and"
            " exit with its exit code. This is how a reviewer tests; the same command and"
            " exit code are the reproduction its verdict carries."
        ),
    )
    loop.add_argument(
        "--record",
        metavar="FILE",
        default=None,
        help=(
            "Record a reviewer's answers from a JSON file (or - for stdin): a list of"
            " {lane, verdict, evidence, why, reproduction: {command, exit_code}, check,"
            " declare}. Requires --reviewer and --work-order. Every reproduction is re-run"
            " in a fresh container and an answer that does not reproduce is refused; with"
            " Docker unavailable nothing is recorded."
        ),
    )
    loop.add_argument(
        "--findings",
        action="store_true",
        help="List the open findings, cannot-tells and resolved findings for --work-order.",
    )
    loop.add_argument(
        "--status",
        action="store_true",
        help=(
            "Whether --work-order's review still blocks it: no dispatch, an unanswered"
            " lane, or an open finding. Exits 1 while it blocks."
        ),
    )

    review_cmd.add_argument(
        "--reviewer", default=None, help="With --record: the reviewer whose answers these are."
    )
    review_cmd.add_argument(
        "--credential",
        default=None,
        help=(
            "With --record: the credential --dispatch issued to this reviewer. Also read from"
            " a `credential` key in the answers file, where the reviewer puts it."
        ),
    )
    review_cmd.add_argument(
        "--work-order",
        dest="work_order",
        default=None,
        help="The work order under review; the round, answers and filed tasks land on it.",
    )
    review_cmd.add_argument(
        "--as-tasks",
        dest="as_tasks",
        action="store_true",
        help=(
            "With --findings, file each open finding as a task on the work order, through"
            " the admission gate that files machine-proposed tasks. Exits 1 when any"
            " finding could not be filed. An unfiled finding still blocks the work order."
        ),
    )
    review_cmd.add_argument(
        "--project",
        dest="project_id",
        default=None,
        help="With --as-tasks: the project id. Read from the work order when omitted.",
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

    refusal = _companion_flags(args)
    if refusal:
        print(f"ds review: {refusal}", file=sys.stderr)
        return 2

    db_path = _db_path(source_root, dream_studio_home)
    # The doors about a review that already happened convene nothing: convening the bench
    # to answer them would be a report about one change set wearing another's questions.
    if getattr(args, "record", None):
        return _record_answers(args, db_path=db_path, source_root=source_root)
    if getattr(args, "findings", None):
        return _show_findings(args, db_path=db_path)
    if getattr(args, "status", None):
        return _show_status(args, db_path=db_path)
    if getattr(args, "run", None):
        return _run_in_lane(args, db_path=db_path)

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

    if getattr(args, "dispatch", None):
        return _dispatch(args, report, paths, db_path=db_path, repo_root=repo_root or source_root)

    print(json.dumps(report, indent=2, sort_keys=True) if args.json else _render(report))
    # "unchecked" is a deliberate listing, not a failure -- but it is not a pass either.
    return 1 if report["status"] == "fail" else 0


def _companion_flags(args: argparse.Namespace) -> str | None:
    """A flag that only means something beside another is refused alone, not ignored.

    Found by the bench's first convening of this surface: --as-tasks and --reviewer used
    without their companion were silently dropped and the command exited 0, so an operator
    who asked for tasks got none and was told it worked.
    """
    if getattr(args, "as_tasks", None) and not getattr(args, "findings", None):
        return "--as-tasks only means something with --findings"
    if getattr(args, "reviewer", None) and not getattr(args, "record", None):
        return "--reviewer only means something with --record"
    if getattr(args, "credential", None) and not getattr(args, "record", None):
        return "--credential only means something with --record"
    if getattr(args, "project_id", None) and not getattr(args, "as_tasks", None):
        return "--project only means something with --findings --as-tasks"
    needs_wo = [f for f in ("record", "findings", "status", "run") if getattr(args, f, None)]
    if needs_wo and not getattr(args, "work_order", None):
        return f"--{needs_wo[0]} needs --work-order"
    if getattr(args, "record", None) and not getattr(args, "reviewer", None):
        return "--record needs --reviewer"
    return None


def _db_path(source_root: Path, dream_studio_home: Path | None) -> Path:
    """The authority this invocation reads and writes, resolved the way every door does."""
    from core.installed_runtime import resolve_installed_runtime_paths

    return resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    ).sqlite_path


def _review_sha(args: argparse.Namespace, repo_root: Path) -> str:
    """The commit this round reviews: the PR head with --pr, otherwise HEAD."""
    from core.gates.lane_sandbox import resolve_sha

    if not args.pr:
        return resolve_sha("HEAD", repo_root=repo_root)
    head = subprocess.run(
        ["gh", "pr", "view", str(args.pr), "--json", "headRefOid", "-q", ".headRefOid"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GH_TIMEOUT_SECONDS,
    )
    sha = (head.stdout or "").strip()
    if head.returncode != 0 or not sha:
        raise RuntimeError(f"could not read the head commit of PR {args.pr}")
    subprocess.run(
        ["git", "fetch", "-q", "origin", f"pull/{args.pr}/head"],
        cwd=str(repo_root),
        capture_output=True,
        timeout=GH_TIMEOUT_SECONDS,
    )
    return resolve_sha(sha, repo_root=repo_root)


def _dispatch(
    args: argparse.Namespace,
    report: dict,
    paths: list[str] | None,
    *,
    db_path: Path,
    repo_root: Path,
) -> int:
    from core.gates.round_table import assignments

    plan: dict = {
        "change_set": paths if paths is not None else "(local working tree)",
        "assignments": assignments(report),
    }
    if not args.work_order:
        plan["recorded"] = False
        plan["note"] = (
            "preview only: pass --work-order to build the lane image and record this round"
        )
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    from core.gates import lane_sandbox
    from core.work_orders.review_answers import record_dispatch, work_order_project

    if work_order_project(args.work_order, db_path=db_path) is None:
        print(f"ds review --dispatch: no work order {args.work_order!r}", file=sys.stderr)
        return 2
    ok, why_not = lane_sandbox.docker_available()
    if not ok:
        print(
            f"ds review --dispatch: {why_not} A lane tests in a container; without one there"
            " is no review to dispatch.",
            file=sys.stderr,
        )
        return 2
    try:
        sha = _review_sha(args, repo_root)
        image = lane_sandbox.build_image(sha, repo_root=repo_root)
    except RuntimeError as exc:
        print(f"ds review --dispatch: {exc}", file=sys.stderr)
        return 2

    try:
        doc = record_dispatch(
            args.work_order,
            sha=sha,
            image=image,
            change_set=plan["change_set"],
            assignments=plan["assignments"],
            db_path=db_path,
            project_root=repo_root,
        )
    except ValueError as exc:
        print(f"ds review --dispatch: {exc}", file=sys.stderr)
        return 2
    if not args.pr and _tree_is_dirty(repo_root):
        doc["warning"] = (
            f"uncommitted changes are NOT in this review: the lane image is commit"
            f" {sha[:12]}. Commit first to have them reviewed."
        )
    doc["run"] = f'ds review --run "<command>" --work-order {args.work_order}'
    print(json.dumps(doc, indent=2, sort_keys=True))
    return 0 if doc.get("stored") else 1


def _tree_is_dirty(repo_root: Path) -> bool:
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return bool((proc.stdout or "").strip())


def _run_in_lane(args: argparse.Namespace, *, db_path: Path) -> int:
    from core.gates import lane_sandbox
    from core.work_orders.review_answers import read_dispatch

    dispatch = read_dispatch(args.work_order, db_path=db_path)
    if dispatch is None:
        print(
            f"ds review --run: no dispatch recorded for {args.work_order}; run"
            f" `ds review --dispatch --work-order {args.work_order}` first.",
            file=sys.stderr,
        )
        return 2
    ok, why_not = lane_sandbox.docker_available()
    if not ok:
        print(f"ds review --run: {why_not}", file=sys.stderr)
        return 2
    run = lane_sandbox.run_in_lane(str(dispatch["image"]), args.run)
    print(run["output_tail"], end="" if run["output_tail"].endswith("\n") else "\n")
    print(
        f"[lane {dispatch['image']}] exit_code={run['exit_code']}"
        f"{' (timed out)' if run['timed_out'] else ''}",
        file=sys.stderr,
    )
    if run["timed_out"]:
        return 124
    return int(run["exit_code"])


def _submission_credential(source: str) -> str | None:
    """A `credential` key in an answers file that wraps its list in an object."""
    try:
        doc = json.loads(Path(source).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return str(doc.get("credential")) if isinstance(doc, dict) and doc.get("credential") else None


def _load_answers(source: str) -> tuple[list | None, str | None]:
    """The submission as a list, or a reason it is not one. Never an empty guess."""
    try:
        raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"cannot read {source}: {exc.strerror or exc}"
    try:
        answers = json.loads(raw)
    except ValueError as exc:
        return None, f"{source} is not JSON: {exc}"
    if isinstance(answers, dict):
        # A reviewer that wrapped its list in {"lanes": [...]} answered correctly and
        # formatted differently. Any OTHER object is refused: the first convening found
        # one silently becoming an empty submission that overwrote a real answer.
        for key in ("lanes", "answers"):
            if isinstance(answers.get(key), list):
                return answers[key], None
        return None, "expected a list of answers, or an object holding one under lanes/answers"
    if not isinstance(answers, list):
        return None, "expected a list of answers"
    return answers, None


def _record_answers(args: argparse.Namespace, *, db_path: Path, source_root: Path) -> int:
    answers, problem = _load_answers(args.record)
    if problem:
        print(f"ds review --record: {problem}", file=sys.stderr)
        return 2

    from core.work_orders.review_answers import record_answers

    credential = getattr(args, "credential", None)
    if not credential and args.record != "-":
        credential = _submission_credential(args.record)
    result = record_answers(
        args.work_order,
        args.reviewer,
        answers,
        credential=credential,
        db_path=db_path,
        project_root=Path(args.repo) if args.repo else source_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if "refused_submission" in result:
        return 2
    # Accepted answers are stored even beside refused ones -- dropping them would punish
    # the lanes answered properly -- but the submission is not a complete review.
    return 0 if result["complete"] else 1


def _show_findings(args: argparse.Namespace, *, db_path: Path) -> int:
    from core.work_orders.review_answers import review_status, work_order_project

    project_id = work_order_project(args.work_order, db_path=db_path)
    if project_id is None:
        print(f"ds review --findings: no work order {args.work_order!r}", file=sys.stderr)
        return 2
    status = review_status(args.work_order, db_path=db_path)
    out: dict = {
        "work_order_id": args.work_order,
        "findings": status["open_findings"],
        "cannot_tell": status["cannot_tell"],
        "resolved": status["resolved"],
        "unanswered": status["unanswered"],
    }
    code = 0
    if args.as_tasks:
        from core.work_orders.review_answers import file_findings_as_tasks

        out["filed"] = file_findings_as_tasks(
            args.work_order, project_id=args.project_id or project_id, db_path=db_path
        )
        if out["filed"].get("unfiled"):
            code = 1
    print(json.dumps(out, indent=2, sort_keys=True))
    return code


def _show_status(args: argparse.Namespace, *, db_path: Path) -> int:
    from core.work_orders.review_answers import review_status, work_order_project

    if work_order_project(args.work_order, db_path=db_path) is None:
        print(f"ds review --status: no work order {args.work_order!r}", file=sys.stderr)
        return 2
    status = review_status(args.work_order, db_path=db_path)
    print(json.dumps(status, indent=2, sort_keys=True))
    return 1 if status["blocking"] else 0
