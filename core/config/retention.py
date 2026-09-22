"""Disk retention for the operator-local Dream Studio store.

Dream Studio writes to several local stores -- an event spool, session
diagnostics, database backups -- and until this module none of them had a
retention policy. `core.upgrade.retention_policy` describes what *should*
happen to database tables, but it is explicitly design-only and has never had
an executor; nothing at all governed the filesystem.

Measured on the operator's machine 2026-09-21, after roughly four months of
use: 10.6 GB across the store, including 482,203 processed spool files,
286,071 failed ones, and four separate full copies of a 1.1 GB database. The
event spool alone held 768,572 files, enough that walking it timed out
repeatedly. Nothing was broken -- every writer worked exactly as designed. The
defect was that no component owned deletion.

Two entry points:

    sweep()   enforces the budgets; the daily maintenance path calls this.
    audit()   reports violations without deleting, so growth is visible
              before it is a problem.

The guard against a regression is BUDGETS itself plus
tests/unit/test_disk_retention.py, which fails when a directory appears under
the store root that no budget and no exemption covers. A new store cannot be
added without someone deciding how it dies.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from core.config import paths


@dataclass(frozen=True)
class Budget:
    """How one store is allowed to grow.

    max_age_days  delete entries last modified before the cutoff.
    keep_newest   keep only the N newest entries, whatever their age.
    glob          restrict the budget to matching entries (default: all).
    entry_is_dir  operate on immediate subdirectories rather than files.
    """

    name: str
    relpath: str
    max_age_days: int | None = None
    keep_newest: int | None = None
    max_bytes: int | None = None
    glob: str = "*"
    entry_is_dir: bool = False
    note: str = ""


#: Every directory under the store root must be named here or in EXEMPT, or the
#: retention test fails. That is the whole point: unbudgeted growth becomes a
#: test failure rather than a surprise four months later.
BUDGETS: tuple[Budget, ...] = (
    Budget(
        name="spool_processed",
        relpath="events/processed",
        max_age_days=7,
        note="already ingested; the event store is the record, not these files",
    ),
    Budget(
        name="spool_failed",
        relpath="events/failed",
        max_age_days=30,
        note="kept longer than processed: the only evidence of an ingest bug",
    ),
    Budget(
        name="spool_failed_reasons",
        relpath="events/failed/reasons",
        max_age_days=30,
        note=(
            "the per-failure reason sidecars. Held 285,828 entries when this "
            "module was written -- and the first draft of the guard missed them, "
            "because it only looked at the store root. Hence DELEGATING."
        ),
    ),
    Budget(
        name="spool_archives",
        relpath="events/archives",
        max_age_days=90,
    ),
    Budget(
        name="diagnostics",
        relpath="diagnostics",
        max_age_days=14,
        max_bytes=512 * 1024**2,
        entry_is_dir=True,
        note=(
            "disposable evidence-of-work, one directory per day. The cap is small "
            "on purpose: this store is defined as disposable, yet one day held "
            "1.86 GB because a session parked two 930 MB database copies here. "
            "Pytest captures and lint output do not need half a gigabyte; "
            "anything that does belongs in backups/, under its own budget."
        ),
    ),
    Budget(
        name="db_premigration_backups",
        relpath="state/backups",
        glob="studio-pre-*.db",
        keep_newest=2,
        note="rollback points; two is enough to step back across a bad migration",
    ),
    Budget(
        name="db_snapshot_backups",
        relpath="backups",
        keep_newest=2,
        entry_is_dir=True,
    ),
    Budget(
        name="logs",
        relpath="logs",
        max_age_days=14,
    ),
    Budget(
        name="session_and_date_sentinels",
        relpath="state",
        glob=".*-*",
        max_age_days=7,
        note=(
            "One-shot markers: .nagged-<session>, .swept-<date>, "
            ".update-checked-<date>, .gh-auth-failed-<token>. Each is a tiny "
            "file whose only job is 'this already happened', and each is created "
            "per session or per day -- which is precisely the shape that filled "
            "this store with 768,572 files. Cheap to recreate, so expire them."
        ),
    ),
    Budget(
        name="hook_queue_orphans",
        relpath="state",
        glob="hookq.*.jsonl",
        max_age_days=2,
        note=(
            "rotated hook-queue files a drain did not finish. The next drain "
            "recovers them, so one surviving two days means draining is broken -- "
            "and a broken drain must not become the next unbounded store."
        ),
    ),
    Budget(
        name="context_packets",
        relpath="context-packets",
        max_age_days=30,
    ),
    Budget(
        name="sessions",
        relpath="sessions",
        max_age_days=30,
    ),
)

#: Directories that are not swept themselves but whose children must each carry
#: a budget, checked recursively. The first draft of this module exempted
#: "events" outright and so never noticed events/failed/reasons, which by then
#: held 285,828 files -- the exact failure mode this module exists to prevent,
#: reproduced inside the guard. An exemption has to be a decision about a
#: subtree, not just about a name.
DELEGATING: frozenset[str] = frozenset({"events", "events/failed"})

#: Directories holding authority or live state, never swept here. Listed
#: explicitly so the test can tell "decided to keep" from "forgotten".
EXEMPT: frozenset[str] = frozenset(
    {
        # Live spool stages. These hold work that has NOT been durably recorded
        # yet -- a pending file, a file mid-ingest, live session state. Deleting
        # on an age rule here loses events, so they are exempt on purpose. If one
        # of them grows, the ingester is stuck and the fix is the ingester.
        "events/spool",
        "events/processing",
        "events/.sessions",
        "state",  # studio.db and friends; the database owns its own retention
        "meta",
        "projects",
        "work-orders",
        "planning",
        "config",
        "adapters",
        "integrations",
        "router",
        "bin",
        ".sessions",
    }
)


@dataclass
class StoreResult:
    name: str
    removed: int = 0
    bytes_freed: int = 0
    kept: int = 0
    error: str | None = None


def _entry_size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except OSError:
        return 0


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def _entries(root: Path, budget: Budget) -> list[os.DirEntry]:
    """Immediate children matching the budget, as DirEntry to avoid a second stat."""
    out: list[os.DirEntry] = []
    try:
        with os.scandir(root) as it:
            for e in it:
                if budget.entry_is_dir and not e.is_dir(follow_symlinks=False):
                    continue
                if not budget.entry_is_dir and not e.is_file(follow_symlinks=False):
                    continue
                if budget.glob != "*" and not Path(e.name).match(budget.glob):
                    continue
                out.append(e)
    except OSError:
        return []
    return out


def sweep_one(budget: Budget, *, dry_run: bool = False) -> StoreResult:
    """Enforce one budget. Never raises; a store that cannot be read is reported."""
    result = StoreResult(name=budget.name)
    root = paths.user_data_dir() / budget.relpath
    if not root.is_dir():
        return result

    entries = _entries(root, budget)
    doomed: list[os.DirEntry] = []

    if budget.max_age_days is not None:
        cutoff = time.time() - budget.max_age_days * 86400
        for e in entries:
            try:
                if e.stat().st_mtime < cutoff:
                    doomed.append(e)
            except OSError:
                continue

    if budget.keep_newest is not None:
        try:
            ordered = sorted(entries, key=lambda e: e.stat().st_mtime, reverse=True)
        except OSError:
            ordered = list(entries)
        keep = budget.keep_newest
        doomed.extend(ordered[keep:])

    if budget.max_bytes is not None:
        # AGE ALONE IS NOT A BUDGET. A single day of diagnostics reached 1.86 GB
        # and an age rule kept every byte of it, because it was recent. Size is
        # the constraint that actually protects the disk; age just decides which
        # entries go first. Newest-first, dropping the oldest until under cap.
        try:
            ordered = sorted(entries, key=lambda e: e.stat().st_mtime, reverse=True)
        except OSError:
            ordered = list(entries)
        running = 0
        for e in ordered:
            running += _entry_size(Path(e.path))
            if running > budget.max_bytes:
                doomed.append(e)

    seen: set[str] = set()
    for e in doomed:
        if e.path in seen:
            continue
        seen.add(e.path)
        p = Path(e.path)
        size = _entry_size(p)
        if not dry_run:
            try:
                _remove(p)
            except OSError as exc:
                result.error = str(exc)
                continue
        result.removed += 1
        result.bytes_freed += size

    result.kept = len(entries) - result.removed
    return result


def sweep(*, dry_run: bool = False) -> list[StoreResult]:
    """Enforce every budget. Safe to call on a schedule; safe to call twice."""
    return [sweep_one(b, dry_run=dry_run) for b in BUDGETS]


def sweep_daily() -> list[StoreResult]:
    """Run the sweep at most once a day, and never on a caller's hot path.

    Scanning half a million spool files is not free, so this must not ride on
    every prompt -- which is exactly the mistake that put a 1.1 GB database copy
    on the UserPromptSubmit path. The sentinel is a dated file, so a crashed
    sweep simply retries tomorrow.
    """
    stamp = paths.state_dir() / f".swept-{time.strftime('%Y-%m-%d')}"
    try:
        if stamp.exists():
            return []
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text("", encoding="utf-8")
    except OSError:
        return []
    return sweep()


def _children_of(rel: str) -> list[str]:
    """Immediate subdirectory names under a store-relative path."""
    root = paths.user_data_dir() / rel if rel else paths.user_data_dir()
    try:
        with os.scandir(root) as it:
            return [e.name for e in it if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []


def unbudgeted_dirs() -> list[str]:
    """Store directories that no budget and no exemption covers.

    This is the regression guard. A new store shows up here the moment it is
    created, and the retention test turns that into a failure. Descends into
    DELEGATING parents, because an exemption granted to a parent must not
    silently cover children nobody has looked at.
    """
    if not paths.user_data_dir().is_dir():
        return []
    budgeted = {b.relpath for b in BUDGETS}
    out: list[str] = []
    # "" is the store root; each DELEGATING parent is then checked in turn.
    for parent in ["", *sorted(DELEGATING)]:
        for name in _children_of(parent):
            rel = f"{parent}/{name}" if parent else name
            if rel in budgeted or rel in EXEMPT or rel in DELEGATING:
                continue
            out.append(rel)
    return sorted(out)


#: A worktree older than this with no uncommitted work is almost certainly a
#: dead agent's, not an operator's.
STALE_WORKTREE_DAYS = int(os.environ.get("DS_STALE_WORKTREE_DAYS", "3"))


def stale_worktrees(repo_root: Path | None = None) -> list[tuple[str, int]]:
    """Registered git worktrees that look abandoned: (path, megabytes).

    Agents create a worktree per task and do not always remove it. Eleven of them
    were found holding 572 MB, every one belonging to a session that had ended,
    plus five registrations whose directories were already gone. They live in a
    temp scratchpad rather than the Dream Studio store, so no budget above can see
    them -- this reports them so they stop being a surprise.

    Reporting only. Deleting someone's checkout is the operator's call, and one of
    those eleven held uncommitted work.
    """
    import subprocess  # noqa: PLC0415 - only needed on the audit path

    root = repo_root or Path.cwd()
    try:
        out = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []

    paths = [ln.split(" ", 1)[1].strip() for ln in out.splitlines() if ln.startswith("worktree ")]
    cutoff = time.time() - STALE_WORKTREE_DAYS * 86400
    stale: list[tuple[str, int]] = []
    for raw in paths[1:]:  # paths[0] is the main checkout
        p = Path(raw)
        try:
            if not p.is_dir() or p.stat().st_mtime > cutoff:
                continue
            if _has_unmerged_work(p, root):
                continue
            size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        except OSError:
            continue
        stale.append((str(p), int(size / 1048576)))
    return stale


def _has_unmerged_work(worktree: Path, repo_root: Path) -> bool:
    """True if this worktree holds commits or edits that exist nowhere else.

    AGE AND A CLEAN TREE ARE NOT EVIDENCE THAT WORK IS FINISHED. The first draft
    of this audit judged on those two alone and flagged eleven worktrees; two of
    them -- ds-lanes on feat/lane-determinism, three hours old, and ds-push-wt --
    held commits that were not on main. Acting on that list would have discarded
    them. "Is it merged?" is the question that actually distinguishes debris from
    work someone is not finished with.

    Errs toward keeping: anything that cannot be determined counts as unmerged.
    """
    import subprocess  # noqa: PLC0415

    try:
        if subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(worktree),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        ).stdout.strip():
            return True  # uncommitted changes

        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(worktree),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        ).stdout.strip()
        if not head:
            return True

        contains = subprocess.run(
            ["git", "branch", "-a", "--contains", head],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        ).stdout
        return not any(
            ln.strip().lstrip("* ").endswith(("main", "master")) for ln in contains.splitlines()
        )
    except (OSError, subprocess.SubprocessError):
        return True


def audit() -> list[str]:
    """Human-readable violations, without deleting anything."""
    problems = [f"{d}/ has no retention budget" for d in unbudgeted_dirs()]
    for r in sweep(dry_run=True):
        if r.removed:
            mb = r.bytes_freed / 1048576
            problems.append(f"{r.name}: {r.removed} entries over budget ({mb:.0f} MB)")
    stale = stale_worktrees()
    if stale:
        total = sum(mb for _, mb in stale)
        problems.append(
            f"{len(stale)} stale git worktree(s) holding {total} MB - "
            f"review with `git worktree list`, remove with `git worktree remove <path>`"
        )
    return problems
