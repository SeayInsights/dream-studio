"""Provenance envelope for gate-consumed artifacts (WO-VERIFY-PROVENANCE).

The 2026-08-18 enforcement audit found that every close-gate artifact
(review_verdict, security_scan, api_contract, milestone audits) is stored as
bare text: not tied to a commit, not attributable to a generator, and
therefore satisfiable by a stale or hand-written file. This module wraps
artifact content in a JSON envelope carrying generator identity, creation
time, and the repo HEAD at write time, so gates can reject artifacts that
lack provenance or predate newer work.

Storage format (in the artifact table's ``content`` column, or the disk
fallback file)::

    {"__ds_envelope__": 1,
     "generator": "ds work-order verify",
     "created_at": "<UTC ISO>",
     "head_commit_sha": "<git rev-parse HEAD or null>",
     "content": "<original artifact text>"}

Legacy artifacts (bare text written before this change) unwrap to
``(text, None)`` — readable everywhere, but gates that REQUIRE provenance
(independent_review) fail them with a regeneration message.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ENVELOPE_MARKER = "__ds_envelope__"
ENVELOPE_VERSION = 1


def wrap(
    content: str,
    *,
    generator: str,
    head_commit_sha: str | None,
    created_at: str | None = None,
) -> str:
    """Wrap artifact text in a provenance envelope; returns the stored string."""
    return json.dumps(
        {
            ENVELOPE_MARKER: ENVELOPE_VERSION,
            "generator": generator,
            "created_at": created_at or datetime.now(UTC).isoformat(),
            "head_commit_sha": head_commit_sha,
            "content": content,
        },
        indent=2,
    )


def unwrap(stored: str | None) -> tuple[str | None, dict[str, Any] | None]:
    """Return ``(content, envelope | None)`` for a stored artifact string.

    Bare text (legacy, pre-envelope) returns ``(stored, None)``. The envelope
    dict, when present, carries ``generator``, ``created_at``,
    ``head_commit_sha``.
    """
    if stored is None:
        return None, None
    text = stored.lstrip()
    if not text.startswith("{"):
        return stored, None
    try:
        obj = json.loads(stored)
    except (json.JSONDecodeError, ValueError):
        return stored, None
    if not isinstance(obj, dict) or ENVELOPE_MARKER not in obj:
        return stored, None
    envelope = {k: v for k, v in obj.items() if k != "content"}
    content = obj.get("content")
    return (content if isinstance(content, str) else stored), envelope


def git_head_sha(project_root: Path | None) -> str | None:
    """HEAD commit of the repo at ``project_root``; None when unavailable."""
    if project_root is None:
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


def commits_after(sha: str, project_root: Path | None) -> list[str] | None:
    """All commits in ``<sha>..HEAD`` — the whole-repo staleness signal.

    Used by milestone artifact gates, where an audit (security/hardening/
    design) covers the whole surface and ANY commit after it potentially
    invalidates it. Returns None when the question cannot be answered.
    """
    if project_root is None:
        return None
    try:
        result = subprocess.run(
            ["git", "log", f"{sha}..HEAD", "--format=%H"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [h for h in result.stdout.strip().splitlines() if h]


def wo_commits_after(
    sha: str,
    project_root: Path | None,
    work_order_id: str,
    title: str | None = None,
) -> list[str] | None:
    """Commits after ``sha`` that reference the work order — the staleness signal.

    Searches ``<sha>..HEAD`` with the same patterns verify uses to collect
    evidence (full id, short id, ``Work-Order:`` trailer, title token), so a
    verdict graded at ``sha`` is stale exactly when new WO-attributed commits
    landed after it. Returns None when the question cannot be answered (no
    git, unknown sha) — callers decide whether unknown counts as stale.
    """
    if project_root is None:
        return None
    patterns: list[str] = [work_order_id, work_order_id[:8], f"Work-Order: {work_order_id}"]
    if title:
        token = title.split(" - ")[0].strip()
        if token and token not in patterns:
            patterns.append(token)
    found: list[str] = []
    for pattern in patterns:
        try:
            result = subprocess.run(
                [
                    "git",
                    "log",
                    f"{sha}..HEAD",
                    "--fixed-strings",
                    f"--grep={pattern}",
                    "--format=%H",
                ],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            # Unknown sha / not a repo — staleness cannot be determined.
            return None
        found.extend(h for h in result.stdout.strip().splitlines() if h)
    # Preserve order, drop duplicates across patterns.
    return list(dict.fromkeys(found))
