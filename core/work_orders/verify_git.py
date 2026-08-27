"""Git evidence collection for work-order verify.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/verify.py``. Holds the
git-commit collection (multi-pattern search + branch fallback), the
authority-evidence fallback summary, and migration-file discovery in a diff.
No logic changes — extracted verbatim from the original module.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

# ── Git diff collection ─────────────────────────────────────────────────────────


from typing import Callable

from core.work_orders.project_roots import ProjectRoots, git_kind


def _collect_git_commits(
    source_root: Path, work_order_id: str, title: str | None = None
) -> str | None:
    """Collect commit diffs referencing this work order.

    Searches git history using multiple patterns so squash-merged WOs are still
    found even when the commit subject does not carry the UUID:

    1. Full UUID (``work_order_id``) — exact match.
    2. Short 8-char id (``work_order_id[:8]``) — legacy and short-log references.
    3. ``Work-Order: <uuid>`` trailer in commit body — squash-merge convention.
    4. WO title token (the part before ' - ', e.g. 'WO-DEBT-I') — squash-merge
       subjects carry the WO name.
    5. Branch name containing the short id — commits reachable from a branch whose
       name includes the WO id fragment.

    Returns None when no pattern matches: callers must treat this as "no evidence",
    NOT as a certified pass and NOT as an auto-score-0 verdict.
    """
    full_id = work_order_id
    short_id = work_order_id[:8]
    trailer_pattern = f"Work-Order: {full_id}"

    # Build ordered pattern list (most precise first).
    patterns: list[str] = [full_id, short_id, trailer_pattern]
    if title:
        token = title.split(" - ")[0].strip()
        if token and token not in patterns:
            patterns.append(token)

    try:
        lines: list[str] = []
        for pattern in patterns:
            log_result = subprocess.run(
                ["git", "log", "--all", "--fixed-strings", f"--grep={pattern}", "--format=%H"],
                cwd=str(source_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if log_result.stdout.strip():
                lines = log_result.stdout.strip().splitlines()
                break  # Stop at the first pattern that finds commits.

        # Pattern 5: branch-name grep — find branches whose name contains the short id,
        # then collect commits reachable from those branches only (not already found).
        if not lines:
            try:
                branch_result = subprocess.run(
                    ["git", "branch", "--all", "--format=%(refname:short)"],
                    cwd=str(source_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=15,
                )
                matching_branches = [
                    b.strip()
                    for b in branch_result.stdout.splitlines()
                    if short_id in b or full_id in b
                ]
                for branch in matching_branches[:3]:
                    log_result = subprocess.run(
                        ["git", "log", branch, "--format=%H", "--max-count=20"],
                        cwd=str(source_root),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=15,
                    )
                    if log_result.stdout.strip():
                        lines = log_result.stdout.strip().splitlines()
                        break
            except Exception:
                pass  # Branch lookup is best-effort; fall through to None.

        if not lines:
            return None

        diff_parts: list[str] = []
        for commit_hash in lines[:10]:
            commit_hash = commit_hash.strip()
            if not commit_hash:
                continue
            show_result = subprocess.run(
                ["git", "show", "--stat", "--patch", "--no-color", commit_hash],
                cwd=str(source_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            diff_parts.append(f"=== commit {commit_hash} ===\n{show_result.stdout[:8000]}")
        return "\n\n".join(diff_parts) if diff_parts else None
    except Exception as exc:
        return f"(error collecting git commits: {exc})"


def _authority_evidence(
    work_order_id: str,
    tasks: list[dict[str, Any]],
    ac_results: dict[str, list[dict[str, Any]]],
) -> tuple[str, bool]:
    """Summarize the WO's authority-side evidence for grading without a git diff.

    Returns (evidence_text, has_passing_executable_check). The executable AC
    results (SQL-CHECK/TEST-CHECK/API-CHECK) are objective, authority-recorded
    proof the work is done — the certification basis when git evidence is absent
    (WO-FIX-VERIFY-GATE). has_passing_executable_check gates certification: with
    NO executable check at all there is nothing objective to certify, so the
    caller keeps the unreviewable path (no false-done).
    """
    has_passing = False
    lines = [
        f"AUTHORITY EVIDENCE for work order {work_order_id[:8]} (no git-diff context available):",
        "",
    ]
    for t in tasks:
        checks = ac_results.get(t["title"], [])
        lines.append(f"- [{t['status']}] {t['title']}")
        for c in checks:
            verdict = "PASS" if c.get("passed") else "FAIL"
            if c.get("passed"):
                has_passing = True
            lines.append(f"    {c.get('kind', 'CHECK')} {verdict}: {c.get('expr', '')}")
    return "\n".join(lines), has_passing


def _find_migration_files(source_root: Path, git_diff: str) -> list[Path]:
    """Return migration SQL files referenced in the git diff.

    The filename portion comes from untrusted git-diff text, so each candidate is
    resolved and confirmed to live inside the migrations directory — a crafted
    ``../`` segment cannot escape it (defense in depth; WO-GATE-HARDEN-CLEANUP).
    """
    import re

    source_root = Path(source_root)
    migrations_dir = (source_root / "core" / "event_store" / "migrations").resolve()
    found: list[Path] = []
    for match in re.finditer(r"core/event_store/migrations/(\S+\.sql)", git_diff):
        candidate = source_root / "core" / "event_store" / "migrations" / match.group(1)
        resolved = candidate.resolve()
        if not resolved.is_relative_to(migrations_dir):
            continue
        if resolved.is_file() and resolved not in found:
            found.append(resolved)
    return found


# WO-MULTIROOT-REVIEW task 3: collect evidence from EVERY root, and record which ones
# answered.
#
# Before this, verify collected from exactly one root:
#     _search_root = resolve_project_root(work_order_id, db_path) or source_root
#
# For Fulcrum -- a working folder holding 6 repositories and 29 worktrees, with no .git
# of its own -- that single call found nothing, and all 28 open Fulcrum work orders were
# graded with no diff at all. A verdict that silently graded 1 of 6 repositories is
# worse than one that says so, because "no violations found" and "nothing was read" are
# indistinguishable in the output.
#
# The provenance is the deliverable as much as the diff is. Each root reports whether it
# contributed, and an empty result is attributed: unreadable, not a repository, or read
# fine and simply had no commits for this work order. Those are three different facts and
# only one of them is a problem.


def collect_union_evidence(
    work_order_id: str,
    roots: "ProjectRoots",
    *,
    title: str | None = None,
    collector: Callable[..., str | None] | None = None,
) -> tuple[str | None, list[dict[str, object]]]:
    """Return ``(combined_diff, provenance)`` across every root of a project.

    ``combined_diff`` is None when NO root produced evidence -- preserving the existing
    contract that None means "no evidence", never a certified pass and never an
    auto-zero. When several roots contribute, each block is labeled with its root so a
    grader reading the diff can tell which repository a change came from.

    ``provenance`` has one entry per root plus one per unreachable declared path, each
    carrying ``root``, ``kind``, ``contributed`` and ``reason``. A caller records it on
    the verdict; nothing here decides a score.
    """
    collect = collector or _collect_git_commits
    parts: list[str] = []
    provenance: list[dict[str, object]] = []
    multi = len(roots.roots) > 1

    for root in roots.roots:
        kind = git_kind(root) or "unversioned"
        entry: dict[str, object] = {"root": str(root), "kind": kind, "contributed": False}
        try:
            diff = collect(root, work_order_id, title=title)
        except Exception as exc:  # a broken root must not lose the readable ones
            entry["reason"] = f"could not be read: {type(exc).__name__}: {exc}"
            provenance.append(entry)
            continue

        if diff:
            entry["contributed"] = True
            entry["chars"] = len(diff)
            entry["reason"] = "commits found for this work order"
            parts.append(f"=== evidence from root {root} ===\n{diff}" if multi else diff)
        elif kind == "unversioned":
            entry["reason"] = (
                "not a git repository -- git evidence is unavailable here, which is not "
                "the same as no work having been done"
            )
        else:
            entry["reason"] = "read successfully; no commits reference this work order"
        provenance.append(entry)

    for path, why in roots.unreachable:
        provenance.append(
            {"root": str(path), "kind": "unreachable", "contributed": False, "reason": why}
        )

    if not roots.roots:
        provenance.append(
            {
                "root": str(roots.declared) if roots.declared else "(none declared)",
                "kind": "none",
                "contributed": False,
                "reason": roots.reason or "the project resolved to no usable root",
            }
        )

    return ("\n\n".join(parts) if parts else None), provenance


def union_evidence_summary(provenance: list[dict[str, object]]) -> str:
    """One line an operator can read without opening the verdict JSON.

    Says the ratio first, because "1 of 6" is the fact that was invisible.
    """
    if not provenance:
        return "no roots were examined"
    contributed = [p for p in provenance if p.get("contributed")]
    total = len([p for p in provenance if p.get("kind") != "unreachable"])
    head = f"{len(contributed)} of {total} root(s) contributed evidence"
    if not contributed:
        reasons = {str(p.get("reason", "")) for p in provenance}
        return head + " -- " + "; ".join(sorted(r for r in reasons if r))
    names = ", ".join(Path(str(p["root"])).name for p in contributed)
    return f"{head}: {names}"
