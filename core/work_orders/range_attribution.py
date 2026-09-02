"""A range is not an attribution, and neither is a narrower range.

WO 80c0e61b. ``boundary_commit_range`` returns ``start..end`` -- contiguous history. When
several work orders land sequentially on one branch that span contains all of them, and the
grader reads the whole diff and blames one work order for every finding in it.

MEASURED, on work order 1db6de49. Its range ``78b98c1a..38637543`` held **10 commits
belonging to 5 different work orders**. Six review rounds attached 9, then 29, then 66
tasks -- roughly 30 per run -- while every round separately confirmed its own four tasks had
landed and were well tested. None of that was the reviewer being wrong; it answered
honestly about the diff it was handed.

THE FIRST FIX WAS ALSO WRONG, and measuring it is what showed that. It excluded any commit
falling inside another work order's closed boundary. Run against the real range that gave
10 -> 1 own, 9 excluded -- and two of the nine (``4a5221cf`` "a node is complete when its
effect is observable", ``a595db1d`` "the loop can now say what it is waiting on") are
1db6de49's OWN commits. They were dropped because a neighbour's boundary spans them.

The reason is structural, not a tuning problem: a delivery boundary is a TIME RANGE, and
two work orders worked on in the same period have legitimately overlapping ranges. No
subtraction over ranges can separate interleaved work, because both ranges genuinely
contain both sets of commits. A silently narrowed range is exactly as dishonest as a
silently wide one and harder to notice -- it hides work rather than adding it.

SO ATTRIBUTION NEEDS A PER-COMMIT SIGNAL, and this records one. ``record_commit_ownership``
is called wherever a work order's progress is stamped (task-done, close) and appends the
commits since its last stamp to that work order's own list. From then on a commit's owner
is a recorded fact rather than an inference from overlapping windows.

Until a commit has recorded ownership it is never excluded. Positive evidence excludes;
absence never does, and the caller is told how much of what it is grading is unattributed.
Historic ranges keep their full width and say so, which is the honest reading of data that
was never captured.
"""

from __future__ import annotations

import json
import re as _re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_GIT_TIMEOUT = 15
OWNERSHIP_KIND = "report"
OWNERSHIP_KEY = "owned_commits"


class CommitOwnershipNotRecorded(RuntimeError):
    """Ownership could not be written. Distinct from having nothing to write.

    record_commit_ownership returns the commits it recorded, so an empty list used to mean
    both "nothing new since the last stamp" and "the write failed" -- and the caller
    reports commits_recorded only when non-empty, so a failure looked like a quiet no-op
    while attribution kept grading the range at full width.
    """


@dataclass
class Attribution:
    """Which commits in a range belong to the work order, and which demonstrably do not."""

    own: list[str] = field(default_factory=list)
    excluded: dict[str, str] = field(default_factory=dict)  # sha -> owning work order
    note: str = ""

    @property
    def narrowed(self) -> bool:
        return bool(self.excluded)


def _commits_in(expr: str, repo_root: Path) -> list[str]:
    """Full SHAs in ``expr``, newest first. Empty on any git failure."""
    try:
        proc = subprocess.run(
            ["git", "log", "--format=%H", expr],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _subject(sha: str, repo_root: Path) -> str:
    """One commit's subject line, or "" when it cannot be read."""
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%s", sha],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _is_reachable(sha: str, repo_root: Path) -> bool:
    """Is this commit an ancestor of HEAD? A squash merge makes the originals not."""
    try:
        proc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def resolve_squashed(sha: str, *, repo_root: Path) -> str | None:
    """The commit on HEAD that absorbed ``sha``, when a squash merge replaced it.

    GitHub's squash writes each original commit's subject into the merge commit body as a
    ``* <subject>`` bullet. That is a RECORDED link, not an inference, so this searches for
    the commit whose body carries this one's subject as such a bullet.

    Returns None when the subject cannot be read, nothing matches, or MORE THAN ONE commit
    matches -- an ambiguous mapping is not a mapping, and picking the first would be a
    guess wearing an answer's clothes.
    """
    subject = _subject(sha, repo_root)
    if not subject:
        return None
    try:
        proc = subprocess.run(
            [
                "git",
                "log",
                "--format=%H",
                f"--grep=^\\* {_re.escape(subject)}$",
                "--extended-regexp",
                "HEAD",
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    hits = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return hits[0] if len(hits) == 1 else None


def reachable_ownership(
    owned: list[str], *, repo_root: Path
) -> tuple[list[str], dict[str, str], list[str]]:
    """Split recorded ownership into what git can still see.

    Returns ``(reachable, squashed_into, lost)``:

    * ``reachable``  -- still ancestors of HEAD, usable as-is.
    * ``squashed_into`` -- ``{original: squash_commit}`` where the merge commit that
      absorbed it could be identified from its own recorded body.
    * ``lost`` -- recorded, unreachable, and unmappable. Named rather than dropped,
      because "we cannot see this work order's commits any more" and "this work order has
      no neighbours" are different facts that otherwise render identically.
    """
    reachable: list[str] = []
    squashed: dict[str, str] = {}
    lost: list[str] = []
    for sha in owned:
        if _is_reachable(sha, repo_root):
            reachable.append(sha)
            continue
        target = resolve_squashed(sha, repo_root=repo_root)
        if target:
            squashed[sha] = target
        else:
            lost.append(sha)
    return reachable, squashed, lost


def read_owned_commits(work_order_id: str, *, db_path: Path) -> list[str]:
    """Commits this work order has recorded as its own, oldest first."""
    from .artifacts import get_wo_artifact

    raw = get_wo_artifact(
        work_order_id, OWNERSHIP_KIND, instance_key=OWNERSHIP_KEY, db_path=db_path
    )
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return []
    commits = payload.get("commits")
    return [c for c in commits if isinstance(c, str)] if isinstance(commits, list) else []


def record_commit_ownership(
    work_order_id: str,
    *,
    repo_root: Path | None,
    db_path: Path,
    since: str | None = None,
) -> list[str]:
    """Record the commits made for this work order since its last stamp. Returns the new ones.

    Best-effort by construction, like the boundary stamps it rides alongside: progress must
    never fail on bookkeeping. A commit that goes unrecorded is simply unattributed, which
    keeps a range wide rather than making it wrong.
    """
    if repo_root is None:
        return []
    from .artifacts import set_wo_artifact

    known = read_owned_commits(work_order_id, db_path=db_path)
    start = since or (known[-1] if known else None)
    if start is None:
        from .delivery_boundary import read_delivery_boundary

        boundary = read_delivery_boundary(work_order_id, db_path=db_path) or {}
        start = boundary.get("start_commit")
    if not start:
        return []

    fresh = [sha for sha in reversed(_commits_in(f"{start}..HEAD", repo_root)) if sha not in known]
    if not fresh:
        return []

    # RETURNING [] MEANT TWO THINGS AND ONLY ONE WAS TRUE. The caller reports
    # `commits_recorded` when this is non-empty, so a failed write rendered exactly like
    # "no new commits since the last stamp" -- and attribution silently kept the range
    # wide. Best-effort is still right (a task-done must not fail on bookkeeping), but the
    # failure has to be distinguishable from nothing-to-do.
    try:
        stored = set_wo_artifact(
            work_order_id,
            OWNERSHIP_KIND,
            json.dumps({"commits": known + fresh}, indent=2),
            instance_key=OWNERSHIP_KEY,
            db_path=db_path,
            generator="ds work-order (commit ownership)",
            project_root=repo_root,
        )
    except Exception as exc:  # noqa: BLE001 - progress must not fail on bookkeeping
        raise CommitOwnershipNotRecorded(
            f"{len(fresh)} commit(s) could not be recorded as owned "
            f"({type(exc).__name__}: {exc}). Attribution will grade this range at full "
            f"width until they are."
        ) from exc
    if not stored:
        raise CommitOwnershipNotRecorded(
            f"{len(fresh)} commit(s) could not be recorded as owned: the artifact table "
            f"is absent on this authority."
        )
    return fresh


def _ownership_index(db_path: Path, exclude: str) -> dict[str, str]:
    """``{sha: work_order_id}`` from every OTHER work order's recorded ownership."""
    import sqlite3

    index: dict[str, str] = {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return index
    try:
        rows = conn.execute(
            "SELECT work_order_id, content FROM business_work_order_artifacts"
            " WHERE instance_key = ?",
            (OWNERSHIP_KEY,),
        ).fetchall()
    except sqlite3.Error:
        return index
    finally:
        conn.close()

    for wo_id, raw in rows:
        if wo_id == exclude or not raw:
            continue
        try:
            payload = json.loads(raw)
            if isinstance(payload.get("content"), str):
                payload = json.loads(payload["content"])
        except (TypeError, ValueError):
            continue
        for sha in payload.get("commits") or []:
            if isinstance(sha, str):
                index.setdefault(sha, wo_id)
    return index


def _squash_aware_index(
    index: dict[str, str], in_range: set[str], repo_root: Path
) -> tuple[dict[str, str], list[str]]:
    """Extend a neighbour's ownership through the squash that absorbed it.

    Returns ``(extended_index, unmappable)``.

    Without the extension a neighbour's claim silently stops applying the moment their
    branch merges: their recorded SHAs are no longer ancestors of HEAD, so nothing in the
    range matches them and the range reads as having no neighbours at all. Measured on
    1db6de49, whose three commits were squashed into 14b8693c by #687.

    THE SECOND RETURN VALUE EXISTS BECAUSE AN INDEPENDENT REVIEW CAUGHT THE ASYMMETRY.
    This dropped a neighbour's unreachable-and-unmappable commits on the floor while
    ``attribute_range`` went on to report "none of the N commits is recorded as belonging
    to another work order" -- an absence it had not established. The same diff's
    ``reachable_ownership`` insisted on naming exactly that distinction for THIS work
    order's own commits. Candid on one side and silent on the other is worse than either,
    because the silence is invisible next to the candour.
    """
    extended = dict(index)
    unmappable: list[str] = []
    for sha, wo_id in index.items():
        if sha in in_range or _is_reachable(sha, repo_root):
            continue
        target = resolve_squashed(sha, repo_root=repo_root)
        if target and target in in_range:
            extended.setdefault(target, wo_id)
        else:
            unmappable.append(sha)
    return extended, unmappable


def attribute_range(
    work_order_id: str,
    expr: str,
    *,
    repo_root: Path,
    db_path: Path,
) -> Attribution:
    """Split ``expr``'s commits into this work order's own and its neighbours'.

    A commit is excluded ONLY when another work order recorded it as its own. Overlapping
    delivery boundaries are deliberately not used: they are time windows, and interleaved
    work orders have overlapping windows, so subtracting on them drops commits that really
    do belong here -- measured, two of them, on the range this work order exists for.
    """
    all_commits = _commits_in(expr, repo_root)
    if not all_commits:
        return Attribution(own=[], note="")

    owned_raw = read_owned_commits(work_order_id, db_path=db_path)
    in_range = set(all_commits)
    mine = set(owned_raw)
    lost_note = ""
    if owned_raw:
        _reachable, _squashed, _lost = reachable_ownership(owned_raw, repo_root=repo_root)
        mine = set(_reachable) | set(_squashed.values())
        if _squashed:
            lost_note = (
                f" {len(_squashed)} of this work order's recorded commits were squashed "
                f"away and were followed to the merge commit that absorbed them."
            )
        if _lost:
            # A SQUASH THAT CANNOT BE FOLLOWED IS NOT THE SAME AS HAVING NO NEIGHBOURS,
            # and the two rendered identically before this. Say which.
            lost_note += (
                f" {len(_lost)} recorded commit(s) are no longer reachable from HEAD and "
                f"could not be mapped to a merge commit, so this work order's own claim "
                f"over them cannot be applied."
            )
    owners, _unmappable_neighbours = _squash_aware_index(
        _ownership_index(db_path, work_order_id), in_range, repo_root
    )
    if _unmappable_neighbours:
        # Say it on the neighbour side too. "No neighbour claims anything here" and "a
        # neighbour's claim could not be located" are different facts, and only one of
        # them means the range is clean.
        lost_note += (
            f" {len(_unmappable_neighbours)} commit(s) recorded by OTHER work orders are "
            f"unreachable and unmappable, so their claims could not be applied to this "
            f"range — a neighbour's work may be graded here."
        )
    # This work order's own record wins: a commit both sides claim is one worked on for
    # this work order too, and dropping it would hide delivered work.
    excluded = {sha: wo for sha, wo in owners.items() if sha in in_range and sha not in mine}

    own = [sha for sha in all_commits if sha not in excluded]
    unattributed = [sha for sha in own if sha not in mine]

    if excluded:
        others = sorted({wo[:8] for wo in excluded.values()})
        note = (
            f"Range narrowed to this work order's commits: {len(own)} of {len(all_commits)} "
            f"in {expr}. {len(excluded)} commit(s) were recorded as belonging to "
            f"{len(others)} other work order(s) ({', '.join(others)}) and are not graded "
            f"here."
        )
        if unattributed:
            note += (
                f" {len(unattributed)} of the remaining commits have no recorded owner and "
                f"are included on that basis alone."
            )
        note += lost_note
    else:
        note = (
            f"Range NOT narrowed: none of the {len(all_commits)} commits in {expr} is "
            f"recorded as belonging to another work order, so all are graded. Commit "
            f"ownership is recorded going forward at each task-done; a range predating "
            f"that carries its full width, which may include a branch neighbour's work."
        ) + lost_note
    return Attribution(own=own, excluded=excluded, note=note)


def attributed_diff(
    work_order_id: str,
    expr: str,
    *,
    repo_root: Path,
    db_path: Path,
) -> tuple[str | None, str]:
    """``(diff_text, note)`` for only the commits attributable to this work order.

    Falls back to the plain range diff when nothing was excluded, so the common case costs
    one extra ``git log`` and produces byte-identical output to before.
    """
    attribution = attribute_range(work_order_id, expr, repo_root=repo_root, db_path=db_path)
    if not attribution.own:
        return None, attribution.note

    if not attribution.narrowed:
        try:
            proc = subprocess.run(
                ["git", "diff", expr],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            return (proc.stdout if proc.returncode == 0 else None), attribution.note
        except (OSError, subprocess.SubprocessError) as exc:
            return None, f"{attribution.note} (git diff failed: {type(exc).__name__})"

    # Narrowed: show each owned commit on its own. `git show` per commit rather than one
    # range, because the owned commits need not be contiguous once a neighbour's work is
    # removed from the middle.
    parts: list[str] = []
    for sha in reversed(attribution.own):
        try:
            proc = subprocess.run(
                ["git", "show", "--format=commit %H%n%s%n", sha],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0 and proc.stdout.strip():
            parts.append(proc.stdout)
    if not parts:
        return None, attribution.note
    return chr(10).join(parts), attribution.note
