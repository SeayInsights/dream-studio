"""Bulk project registration — intake-lite wrapper for discovered project candidates.

Thin coordinator over core.projects.acquisition.acquire_project.
No full scope interview; registers + stack-detects each candidate in one pass.

Usage:
    from core.projects.bulk_intake import bulk_acquire
    from core.projects.discovery import discover_project_candidates
    from pathlib import Path

    candidates = discover_project_candidates(Path.home() / "builds")
    result = bulk_acquire(candidates, source_root=Path.cwd())
    print(result["registered"])   # list of registered project dicts
    print(result["skipped"])      # already-registered (idempotent)
    print(result["errors"])       # failed acquisitions
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def bulk_acquire(
    candidates: list[dict[str, Any]],
    *,
    source_root: str | Path,
    dream_studio_home: str | Path | None = None,
    write_marker: bool = False,
) -> dict[str, Any]:
    """Register and stack-detect a list of project candidates.

    Only candidates with a local ``path`` are processed — GitHub-only entries
    (path=None, source="github") are collected in ``github_only`` for the caller
    to handle (e.g., clone first).

    Args:
        candidates:        List of candidate dicts from discover_project_candidates().
        source_root:       Dream Studio repo root.
        dream_studio_home: Override Dream Studio home directory.
        write_marker:      Write .dream-studio-project marker to each project. Default False.

    Returns:
        ok           → True (always; per-candidate errors are in ``errors``)
        registered   → list of newly-registered project dicts (ok=True, idempotent=False)
        skipped      → list of already-registered dicts (ok=True, idempotent=True)
        github_only  → list of GitHub-only candidates (no local path)
        errors       → list of {path, name, error} for failed acquisitions
        counts       → {registered, skipped, github_only, errors}
    """
    from core.projects.acquisition import acquire_project

    source = Path(source_root)

    registered: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    github_only: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for candidate in candidates:
        path_str = candidate.get("path")
        name = candidate.get("name", "")

        if not path_str:
            github_only.append(candidate)
            continue

        target = Path(path_str)
        if not target.is_dir():
            errors.append({"path": path_str, "name": name, "error": "path is not a directory"})
            continue

        try:
            result = acquire_project(
                target,
                project_name=name or None,
                write_marker=write_marker,
                run_scan=False,
                source_root=source,
                dream_studio_home=dream_studio_home,
            )
            if not result.get("ok"):
                errors.append({"path": path_str, "name": name, "error": result.get("error", "unknown")})
            elif result.get("idempotent"):
                skipped.append(result)
            else:
                registered.append(result)
        except Exception as exc:
            errors.append({"path": path_str, "name": name, "error": str(exc)})

    return {
        "ok": True,
        "registered": registered,
        "skipped": skipped,
        "github_only": github_only,
        "errors": errors,
        "counts": {
            "registered": len(registered),
            "skipped": len(skipped),
            "github_only": len(github_only),
            "errors": len(errors),
        },
    }
