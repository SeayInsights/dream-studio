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
