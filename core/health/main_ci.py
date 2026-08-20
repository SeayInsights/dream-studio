"""Post-merge CI status for the default branch (WO-MAINRED-VISIBILITY).

The merge rule is satisfied by the 3-platform ``pr-smoke`` matrix, which runs a
focused subset (11 files). The FULL suite runs post-merge, ubuntu-only, in
``full-ci`` — so a merge can be correctly authorized and still break ``main``,
and until now no DS surface reported that. On 2026-08-19 main sat red across
eight merges before an operator noticed; twice more the same day a red was found
only because someone thought to look.

An unwatched signal is an invisible signal — the same class as the enforcement
bypasses this milestone already made visible. This module reads the status; the
doctor / project-state / close surfaces report it.

Read-only and advisory by design: a red ``main`` from anyone's merge must not
block unrelated work. The defect was invisibility, not permissiveness. Never
fabricates a verdict — an unavailable or unauthenticated ``gh`` yields
``status="unknown"`` with the reason.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

_WORKFLOW = "Full CI"
_BRANCH = "main"
_TIMEOUT = 25


def _gh_json(args: list[str], cwd: Path | None) -> tuple[Any, str | None]:
    """Run a ``gh`` command expecting JSON. Returns ``(parsed, error)``."""
    try:
        result = subprocess.run(
            ["gh", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT,
        )
    except FileNotFoundError:
        return None, "gh CLI not installed"
    except subprocess.TimeoutExpired:
        return None, f"gh timed out after {_TIMEOUT}s"
    except OSError as exc:
        return None, f"gh could not run: {exc}"

    # WO-MAINRED-GH-NONSTR: everything below reads two attributes off whatever
    # `subprocess.run` returned, and this reader's documented contract is that any
    # unusable reply becomes unknown-with-reason — never an exception, because it
    # is an ADVISORY check that must not be able to raise into a caller who was
    # asking about something else. A caller that patches subprocess.run (a
    # legitimate thing for a test about a DIFFERENT subprocess call to do) hands
    # back a mock whose .stdout is a truthy non-string, and `stdout or "[]"` fed
    # it straight to json.loads, which raises TypeError — not a subclass of
    # JSONDecodeError or ValueError, so the guard below never saw it. That took
    # main red for a full day. Normalise to text first, then parse.
    def _text(value: Any) -> str:
        return value if isinstance(value, str) else ""

    if not isinstance(result.returncode, int):
        return None, "gh returned no usable exit status"
    if result.returncode != 0:
        detail = (_text(result.stderr) or _text(result.stdout)).strip().splitlines()
        reason = detail[0][:200] if detail else f"gh exited {result.returncode}"
        return None, reason
    raw = _text(result.stdout)
    if not raw.strip():
        # No text at all is a real answer ("no runs yet"), not a parse failure —
        # but it must not be confused with output we simply could not read.
        if result.stdout is not None and not isinstance(result.stdout, str):
            return None, "gh returned non-text output"
        return [], None
    try:
        return json.loads(raw), None
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return None, f"gh returned non-JSON: {exc}"


def main_ci_status(*, repo_root: Path | None = None, limit: int = 5) -> dict[str, Any]:
    """Latest ``full-ci`` conclusion for ``main``.

    Returns::

        {"status": "success" | "failure" | "running" | "unknown",
         "conclusion": str | None,       # raw gh conclusion when finished
         "head_sha": str | None,
         "run_url": str | None,
         "title": str | None,
         "red": bool,                    # True only on a definite failure
         "reason": str | None}           # why status is unknown

    ``red`` is deliberately False when the status is unknown: an unreadable
    signal is reported as unreadable, never as a failure (nor as a pass).
    """
    runs, error = _gh_json(
        [
            "run",
            "list",
            "--branch",
            _BRANCH,
            "--workflow",
            _WORKFLOW,
            "--limit",
            str(limit),
            "--json",
            "conclusion,status,headSha,url,displayTitle",
        ],
        repo_root,
    )
    if error is not None:
        return {
            "status": "unknown",
            "conclusion": None,
            "head_sha": None,
            "run_url": None,
            "title": None,
            "red": False,
            "reason": error,
        }
    if not runs:
        return {
            "status": "unknown",
            "conclusion": None,
            "head_sha": None,
            "run_url": None,
            "title": None,
            "red": False,
            "reason": f"no {_WORKFLOW} runs found for {_BRANCH}",
        }

    latest = runs[0]
    raw_status = (latest.get("status") or "").lower()
    conclusion = (latest.get("conclusion") or "").lower() or None
    if raw_status in ("queued", "in_progress", "waiting", "pending", "requested"):
        status = "running"
    elif conclusion == "success":
        status = "success"
    elif conclusion in ("failure", "timed_out", "startup_failure"):
        status = "failure"
    elif conclusion in ("cancelled", "skipped", "neutral", "stale", "action_required"):
        # Not a pass and not a defect — say so rather than guessing either way.
        status = "unknown"
    else:
        status = "unknown"

    return {
        "status": status,
        "conclusion": conclusion,
        "head_sha": latest.get("headSha"),
        "run_url": latest.get("url"),
        "title": latest.get("displayTitle"),
        "red": status == "failure",
        "reason": None if status in ("success", "failure", "running") else conclusion,
    }


def main_ci_warning(status: dict[str, Any] | None) -> str | None:
    """One-line operator-facing warning for a red ``main``, else None.

    Only a DEFINITE failure warns: 'running' and 'unknown' are not defects, and
    crying wolf on them would train operators to ignore the line that matters.
    """
    if not status or not status.get("red"):
        return None
    sha = (status.get("head_sha") or "")[:8]
    title = (status.get("title") or "").strip()
    url = status.get("run_url") or ""
    return (
        f"main is RED: the latest {_WORKFLOW} run failed at {sha}"
        f"{f' ({title[:70]})' if title else ''}."
        f"{f' See {url}' if url else ''}"
        " pr-smoke green is merge authorization, not proof main is green."
    )
