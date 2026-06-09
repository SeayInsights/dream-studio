"""Project discovery — enumerate candidate project roots for brownfield onboarding.

Two strategies (composed by discover_project_candidates):
  1. Folder walk: scan a directory tree for .git/ dirs and common manifest files.
  2. GitHub enumeration (capability-gated): call `gh repo list` when gh is authed.
     Absent gh → folder walk only, no error raised.

Usage:
    from core.projects.discovery import discover_project_candidates

    candidates = discover_project_candidates(Path.home() / "builds")
    # [{"path": "/home/user/builds/myapp", "name": "myapp", "has_git": True, "markers": ["pyproject.toml"]}, ...]
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

_PROJECT_MARKERS = (
    ".git",
    "package.json",
    "pyproject.toml",
    "setup.py",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "Makefile",
    "composer.json",
)

_SKIP_DIRS = {
    ".venv", "venv", "env", ".env",
    "node_modules", "__pycache__", ".git",
    "dist", "build", "target", ".tox",
}


def _find_project_roots(root: Path, *, max_depth: int = 3) -> list[dict[str, Any]]:
    """Walk root up to max_depth levels, returning dirs that look like project roots."""
    results: list[dict[str, Any]] = []

    def _walk(path: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = list(path.iterdir())
        except PermissionError:
            return

        names = {e.name for e in entries}
        has_git = ".git" in names
        found_markers = [m for m in _PROJECT_MARKERS if m in names and m != ".git"]

        if has_git or found_markers:
            results.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "has_git": has_git,
                    "markers": found_markers,
                    "source": "folder_walk",
                }
            )
            # Don't descend into project subdirs — avoids nested monorepo noise.
            return

        for entry in entries:
            if entry.is_dir() and entry.name not in _SKIP_DIRS and not entry.name.startswith("."):
                _walk(entry, depth + 1)

    _walk(root, 0)
    return results


def _discover_github_repos(entity: str) -> list[dict[str, Any]]:
    """Enumerate repos for a GitHub org or user via `gh repo list`.

    Returns empty list when gh is not authenticated or entity is unreachable.
    Never raises.
    """
    try:
        result = subprocess.run(
            ["gh", "repo", "list", entity, "--json", "name,url,description,isPrivate", "--limit", "100"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        repos = json.loads(result.stdout or "[]")
        return [
            {
                "name": r.get("name", ""),
                "url": r.get("url", ""),
                "description": r.get("description") or "",
                "is_private": r.get("isPrivate", False),
                "source": "github",
                "path": None,
            }
            for r in repos
            if r.get("name")
        ]
    except Exception:
        return []


def _is_gh_authed() -> bool:
    """Return True if `gh auth status` exits 0."""
    try:
        return subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=10).returncode == 0
    except Exception:
        return False


def discover_project_candidates(
    search_root: Path,
    *,
    github_entity: str | None = None,
    max_depth: int = 3,
    include_github: bool = True,
) -> list[dict[str, Any]]:
    """Discover project candidates from a folder walk and optionally GitHub.

    Args:
        search_root:    Root directory to walk.
        github_entity:  GitHub org or username to enumerate repos for.
                        If None and include_github=True, skipped silently.
        max_depth:      Max folder depth to descend (default 3).
        include_github: Whether to attempt GitHub enumeration (default True).
                        Requires gh CLI to be authenticated; absent gh → no-op.

    Returns:
        List of candidate dicts, each with keys:
          path (str|None), name (str), has_git (bool), markers (list),
          source ("folder_walk"|"github"), url (str, GitHub only).

    Never raises.
    """
    try:
        candidates = _find_project_roots(Path(search_root).resolve(), max_depth=max_depth)
    except Exception:
        candidates = []

    if include_github and github_entity and _is_gh_authed():
        gh_repos = _discover_github_repos(github_entity)
        existing_names = {c["name"] for c in candidates}
        for repo in gh_repos:
            if repo["name"] not in existing_names:
                candidates.append(repo)

    return candidates
