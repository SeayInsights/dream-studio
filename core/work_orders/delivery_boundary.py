"""The recorded change-set boundary for a work order (WO-VERIFY-GRADES-DELIVERY).

Verify locates a WO's work by grepping git history for the WO's uuid or its title.
Every one of these breaks that, and none of them means nothing was delivered:

- the commit names the WO by its human tag (``WO-MAINRED-GH-NONSTR``) not its uuid
- the title was reworded after the commit was written, or vice versa
- the work is committed but not pushed, or there is no remote at all
- GitHub's squash-merge rewrote the subject line
- the work is not committed yet — still in the working tree
- the target is not a git repository

A grader that cannot see the work reports "unreviewable", which is honest and
useless, and the practical effect is a close gate that cannot be satisfied for
correctly-delivered work. That is pressure toward ``--force``, which is how
false-done gets normalised.

The fix is to stop *searching* for the boundary and start *recording* it:
``work-order start`` stamps the repo HEAD, so the change set is
``start_commit..HEAD`` with no message conventions involved. History grepping
stays as reinforcement for attribution — never as the locator.

Stored in ``business_work_order_artifacts`` under the existing multi-instance
``report`` kind (``instance_key="delivery_boundary"``), so there is no new table
and no migration. A non-git project records ``start_commit: None`` — absence is
a fact about the repo, not a failure to record.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_INSTANCE_KEY = "delivery_boundary"
_GIT_TIMEOUT = 10


def _git_head(repo_root: Path | None) -> tuple[str | None, str | None]:
    """Current HEAD sha of ``repo_root``. Returns ``(sha, reason_if_none)``.

    Never raises: a WO must start whether or not its repo is readable. A missing
    sha is recorded WITH its reason, so a later reader can tell "no git here"
    from "we forgot to look".
    """
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root) if repo_root else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
        )
    except FileNotFoundError:
        return None, "git not installed"
    except subprocess.TimeoutExpired:
        return None, "git rev-parse timed out"
    except OSError as exc:
        return None, f"git could not run: {exc}"
    if not isinstance(proc.returncode, int) or proc.returncode != 0:
        detail = (proc.stderr if isinstance(proc.stderr, str) else "").strip().splitlines()
        return None, (detail[0][:160] if detail else "git rev-parse failed")
    sha = (proc.stdout if isinstance(proc.stdout, str) else "").strip()
    if not sha:
        return None, "git rev-parse returned no sha (empty repository?)"
    return sha, None


def record_delivery_boundary(
    work_order_id: str,
    *,
    repo_root: Path | None,
    db_path: Path | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Stamp the WO's starting commit. Returns the recorded boundary dict.

    Best-effort by construction: a WO must be startable even when the boundary
    cannot be written, because refusing to start work over a bookkeeping failure
    would be a worse defect than the one this fixes. A failed write is reflected
    in the returned dict rather than raised.
    """
    sha, reason = _git_head(repo_root)
    boundary: dict[str, Any] = {
        "work_order_id": work_order_id,
        "start_commit": sha,
        "started_at": now or datetime.now(UTC).isoformat(),
        "repo_root": str(repo_root) if repo_root else None,
    }
    if reason:
        boundary["start_commit_reason"] = reason

    try:
        from core.work_orders.artifacts import set_wo_artifact

        stored = set_wo_artifact(
            work_order_id,
            "report",
            json.dumps(boundary, indent=2),
            instance_key=_INSTANCE_KEY,
            db_path=db_path,
            generator="ds work-order start (delivery boundary)",
            project_root=repo_root,
        )
        boundary["recorded"] = bool(stored)
    except Exception as exc:  # noqa: BLE001 - starting work must not fail on bookkeeping
        boundary["recorded"] = False
        boundary["record_error"] = f"{type(exc).__name__}: {exc}"[:200]
    return boundary


def read_delivery_boundary(
    work_order_id: str, *, db_path: Path | None = None
) -> dict[str, Any] | None:
    """The recorded boundary, or None when none was ever stamped.

    None means "this WO started before boundaries were recorded" — a distinct
    fact from a boundary that exists with ``start_commit: None`` (a non-git
    project). Callers must not collapse the two: the first says fall back to the
    old locator, the second says this repo has no commits to range over.
    """
    try:
        from core.work_orders.artifacts import get_wo_artifact_envelope

        raw, _envelope = get_wo_artifact_envelope(
            work_order_id, "report", instance_key=_INSTANCE_KEY, db_path=db_path
        )
        if raw is None:
            return None
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _module_boundary_globs(work_order_id: str, db_path: Path | None) -> list[str]:
    """The WO's declared ``Module boundary:`` prefixes, or [] when none.

    Reuses the enforcement lib's parser and matcher rather than re-deriving them:
    two implementations of one boundary rule is how the on-edit hook and verify
    would come to disagree about what a WO owns — the same
    two-copies-one-stale shape this milestone keeps finding.
    """
    try:
        import sqlite3

        from runtime.lib.enforcement import boundary_globs

        conn = sqlite3.connect(str(db_path)) if db_path else None
        if conn is None:
            return []
        try:
            row = conn.execute(
                "SELECT description FROM business_work_orders WHERE work_order_id = ?",
                (work_order_id,),
            ).fetchone()
        finally:
            conn.close()
        return boundary_globs(row[0] if row else "") or []
    except Exception:
        return []


def working_tree_changes(
    work_order_id: str,
    *,
    repo_root: Path | None,
    db_path: Path | None = None,
) -> tuple[list[str], str | None]:
    """Uncommitted paths attributable to this WO. Returns ``(paths, reason)``.

    Work in progress is still delivered work: grading only committed state is why
    an uncommitted deliverable reads as nothing delivered. Covers both tracked
    modifications (``git diff --name-only HEAD``) and untracked files
    (``git ls-files --others --exclude-standard``), because a brand-new module is
    exactly the case a tracked-only diff misses.

    SCOPED to the WO's ``Module boundary:`` when it declares one. Without that
    scoping this layer would sweep in every unrelated dirty file in the same
    checkout and grade it as this WO's delivery — the reverse hazard, and worse
    than the defect it fixes, because it would let a WO be certified by work it
    never did.
    """
    if repo_root is None:
        return [], "no repo root resolved for this work order"

    def _git_lines(args: list[str]) -> tuple[list[str], str | None]:
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_GIT_TIMEOUT,
            )
        except FileNotFoundError:
            return [], "git not installed"
        except subprocess.TimeoutExpired:
            return [], f"git {args[0]} timed out"
        except OSError as exc:
            return [], f"git could not run: {exc}"
        if not isinstance(proc.returncode, int) or proc.returncode != 0:
            return [], f"git {args[0]} failed"
        out = proc.stdout if isinstance(proc.stdout, str) else ""
        return [ln.strip() for ln in out.splitlines() if ln.strip()], None

    tracked, why_tracked = _git_lines(["diff", "--name-only", "HEAD"])
    untracked, why_untracked = _git_lines(["ls-files", "--others", "--exclude-standard"])
    if why_tracked and why_untracked:
        return [], why_tracked

    paths = sorted(set(tracked) | set(untracked))
    if not paths:
        return [], None

    globs = _module_boundary_globs(work_order_id, db_path)
    if not globs:
        # No declared boundary means no basis for attributing a dirty file to this
        # WO. Reported rather than silently returning everything: attributing the
        # whole working tree to a WO that never claimed it is how a WO gets
        # certified by someone else's work.
        return [], (
            f"{len(paths)} uncommitted path(s) present but this work order declares no "
            "'Module boundary:', so none can be attributed to it"
        )

    # FAIL-OPEN vs FAIL-CLOSED: the same predicate needs opposite defaults here.
    # runtime.lib.enforcement.path_in_boundary returns True for a path it cannot
    # resolve relative to the project root — correct for the on-edit hook, whose
    # job is to avoid BLOCKING an edit it cannot classify. For attribution the
    # safe default is inverted: a path we cannot place must not be CLAIMED as this
    # WO's delivery, or an unresolvable path silently certifies a WO with work it
    # never did. So paths are resolved against repo_root first (git reports them
    # repo-relative), and anything still unplaceable is dropped and counted rather
    # than inherited as a match.
    try:
        from runtime.lib.enforcement import path_in_boundary

        scoped: list[str] = []
        unplaceable = 0
        for rel in paths:
            absolute = (Path(repo_root) / rel).as_posix()
            try:
                (Path(repo_root) / rel).resolve().relative_to(Path(repo_root).resolve())
            except (OSError, ValueError):
                unplaceable += 1
                continue
            if path_in_boundary(absolute, str(repo_root), globs):
                scoped.append(rel)
    except Exception as exc:
        return [], f"boundary matching unavailable: {type(exc).__name__}"
    if unplaceable:
        return scoped, (
            f"{unplaceable} uncommitted path(s) could not be placed relative to the repo"
            " root and were NOT attributed to this work order"
        )
    return scoped, None


_MAX_FALLBACK_FILES = 40
_MAX_FALLBACK_BYTES = 200_000


def boundary_file_contents(
    work_order_id: str,
    *,
    repo_root: Path | None,
    db_path: Path | None = None,
) -> tuple[str, str | None]:
    """Current content of the WO's boundary files. Returns ``(text, reason)``.

    The layer that makes this foolproof: it needs no VCS at all. A non-git target,
    a shallow clone with no usable range, a repo whose history was rewritten — in
    every one of those the boundary files still exist on disk, and their content is
    what the WO actually delivered.

    Deliberately the LAST resort, because it shows the current state rather than
    the change: a reviewer sees what the code is, not what this WO did to it. That
    is weaker evidence than a diff and must never displace one — but it is
    infinitely better than "unreviewable", which is what the grader says today when
    the grep misses.

    Bounded (``_MAX_FALLBACK_FILES`` files, ``_MAX_FALLBACK_BYTES`` chars) and the
    truncation is REPORTED, because a silently clipped fallback is a partial
    picture presented as a whole one.
    """
    if repo_root is None:
        return "", "no repo root resolved for this work order"
    globs = _module_boundary_globs(work_order_id, db_path)
    if not globs:
        return "", "this work order declares no 'Module boundary:' to read"

    root = Path(repo_root)
    collected: list[str] = []
    used = 0
    seen = 0
    skipped_missing: list[str] = []

    for glob in globs:
        target = root / glob.rstrip("/")
        candidates: list[Path] = []
        if target.is_file():
            candidates = [target]
        elif target.is_dir():
            candidates = sorted(p for p in target.rglob("*") if p.is_file())
        else:
            skipped_missing.append(glob)
            continue
        for path in candidates:
            if seen >= _MAX_FALLBACK_FILES or used >= _MAX_FALLBACK_BYTES:
                break
            try:
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            seen += 1
            rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
            chunk = f"=== boundary file {rel} ===\n{body}\n"
            collected.append(chunk)
            used += len(chunk)

    if not collected:
        detail = (
            f"none of the declared boundary paths exist: {', '.join(skipped_missing)}"
            if skipped_missing
            else "no readable files under the declared boundary"
        )
        return "", detail

    text = "".join(collected)
    truncated = seen >= _MAX_FALLBACK_FILES or used >= _MAX_FALLBACK_BYTES
    reason = None
    if truncated:
        reason = (
            f"boundary content truncated at {seen} file(s) / {used} chars — this is a"
            " PARTIAL view of the declared boundary"
        )
    elif skipped_missing:
        reason = f"declared boundary path(s) not present: {', '.join(skipped_missing)}"
    return text[:_MAX_FALLBACK_BYTES], reason


def boundary_diff_text(
    work_order_id: str,
    *,
    repo_root: Path | None,
    db_path: Path | None = None,
) -> tuple[str | None, str | None]:
    """The WO's delivered change, from RECORDED state. ``(text, note)``.

    The locator that replaces commit-message archaeology. Layers, strongest first,
    and additive rather than exclusive because each answers a different question:

    1. ``start_commit..HEAD`` — the actual diff of what landed since the WO began.
    2. the uncommitted working tree, boundary-scoped — work in progress is still
       delivered work.
    3. current boundary-file content — the floor that needs no VCS at all.

    Returns ``(None, reason)`` when every layer is empty, which is the ONLY honest
    "nothing to look at". That is a finding about the work (a WO that delivered
    nothing) rather than the metadata artifact "unreviewable" used to mean.

    ``note`` carries every caveat encountered — a truncated fallback, an
    unplaceable path, a missing boundary — so a partial view is never presented as
    a whole one.
    """
    notes: list[str] = []
    sections: list[str] = []

    expr, why = boundary_commit_range(work_order_id, db_path=db_path)
    if expr and repo_root is not None:
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
            if isinstance(proc.returncode, int) and proc.returncode == 0:
                body = (proc.stdout if isinstance(proc.stdout, str) else "").strip()
                if body:
                    sections.append(f"=== commit range {expr} ===\n{body}\n")
            else:
                notes.append(f"git diff {expr} failed")
        except (OSError, subprocess.SubprocessError) as exc:
            notes.append(f"git diff unavailable: {type(exc).__name__}")
    elif why:
        notes.append(why)

    paths, why_tree = working_tree_changes(work_order_id, repo_root=repo_root, db_path=db_path)
    if why_tree:
        notes.append(why_tree)
    if paths and repo_root is not None:
        try:
            proc = subprocess.run(
                ["git", "diff", "HEAD", "--", *paths],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            tracked = (proc.stdout if isinstance(proc.stdout, str) else "").strip()
        except (OSError, subprocess.SubprocessError):
            tracked = ""
        listing = "\n".join(f"  {p}" for p in paths)
        sections.append(
            f"=== uncommitted, within this work order's module boundary ===\n{listing}\n"
            + (f"{tracked}\n" if tracked else "")
        )

    if not sections:
        # Only now is the no-VCS floor worth reading: it shows current state rather
        # than the change, so it must never displace a diff that exists.
        content, why_content = boundary_file_contents(
            work_order_id, repo_root=repo_root, db_path=db_path
        )
        if why_content:
            notes.append(why_content)
        if content:
            sections.append(content)

    if not sections:
        return None, "; ".join(notes) if notes else "no recorded delivery for this work order"
    return "".join(sections), ("; ".join(notes) if notes else None)


def boundary_commit_range(
    work_order_id: str, *, db_path: Path | None = None
) -> tuple[str | None, str | None]:
    """``(range_expr, reason_if_none)`` for the WO's recorded change set.

    ``<start_commit>..HEAD`` when a start commit was recorded — the range needs no
    commit-message convention, survives a squash merge, and is correct for work
    that was never pushed. ``(None, reason)`` when there is nothing to range over,
    and the reason distinguishes the cases so a caller can pick its next layer
    (working tree, boundary-file content) rather than guessing.
    """
    boundary = read_delivery_boundary(work_order_id, db_path=db_path)
    if boundary is None:
        return None, "no delivery boundary recorded (WO started before boundaries were stamped)"
    sha = boundary.get("start_commit")
    if not isinstance(sha, str) or not sha:
        why = boundary.get("start_commit_reason") or "no start commit recorded"
        return None, f"no commit range available: {why}"
    return f"{sha}..HEAD", None
