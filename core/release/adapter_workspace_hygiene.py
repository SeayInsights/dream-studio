"""Adapter workspace hygiene policy for repo-local and user-local state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

ACTIVE_ADAPTER_SURFACES: tuple[str, ...] = ("AGENTS.md", "CLAUDE.md")
GENERATED_ADAPTER_PROJECTION_ROOT = "adapter-projections/"
LOCAL_ADAPTER_EXCLUDE_PATTERNS: tuple[str, ...] = (
    ".claude/worktrees/",
    ".codex/sessions/",
    ".codex/tasks/",
    ".codex/tmp/",
    ".adapter-scratch/",
    ".ai-scratch/",
)
USER_LOCAL_ADAPTER_STATE_ROOTS: tuple[str, ...] = (
    "~/.dream-studio/adapters/",
    "~/.dream-studio/worktrees/",
    "~/.dream-studio/sessions/",
)


def adapter_workspace_policy() -> dict[str, Any]:
    """Return the durable adapter workspace hygiene policy."""

    return {
        "policy_id": "adapter_workspace_hygiene",
        "repo_tracked": [
            "product source",
            "tests",
            "public docs",
            "templates",
            *ACTIVE_ADAPTER_SURFACES,
            f"{GENERATED_ADAPTER_PROJECTION_ROOT}*",
        ],
        "user_local_state": list(USER_LOCAL_ADAPTER_STATE_ROOTS),
        "local_exclude_patterns": list(LOCAL_ADAPTER_EXCLUDE_PATTERNS),
        "repo_gitignore_policy": (
            "Only ignore patterns safe for every checkout; do not hide product source, "
            "active adapter surfaces, or generated adapter projections."
        ),
        "secret_policy": "Classify secret/auth paths by path only; do not read or print values.",
        "unknown_adapter_file_policy": (
            "Classify unknown adapter files before ignore, delete, archive, or cleanup decisions."
        ),
        "live_db_mutation_authorized": False,
    }


def classify_adapter_workspace_path(path: str | Path) -> dict[str, Any]:
    """Classify an adapter-related path without inspecting file contents."""

    normalized = _normalize(path)
    path_lower = normalized.lower()
    if normalized in ACTIVE_ADAPTER_SURFACES:
        category = "active_adapter_projection"
        repo_tracked = True
        local_exclude = False
        generated_projection = False
        manual_review = False
    elif path_lower.startswith(GENERATED_ADAPTER_PROJECTION_ROOT):
        category = "generated_adapter_projection"
        repo_tracked = True
        local_exclude = False
        generated_projection = True
        manual_review = False
    elif _matches_local_exclude(normalized):
        category = "local_adapter_scratch"
        repo_tracked = False
        local_exclude = True
        generated_projection = False
        manual_review = False
    elif _is_user_local_adapter_state(path_lower):
        category = "user_local_adapter_state"
        repo_tracked = False
        local_exclude = False
        generated_projection = False
        manual_review = False
    elif any(marker in path_lower for marker in ("secret", "token", "auth", "credential")):
        category = "sensitive_manual_review"
        repo_tracked = False
        local_exclude = False
        generated_projection = False
        manual_review = True
    else:
        category = "unknown_adapter_file"
        repo_tracked = False
        local_exclude = False
        generated_projection = False
        manual_review = True

    return {
        "path": str(path),
        "normalized_path": normalized,
        "category": category,
        "repo_tracked": repo_tracked,
        "local_exclude_required": local_exclude,
        "generated_projection": generated_projection,
        "requires_manual_review": manual_review,
        "content_inspection_required": False,
    }


def required_local_exclude_patterns() -> tuple[str, ...]:
    """Return repo-local machine-specific adapter scratch patterns."""

    return LOCAL_ADAPTER_EXCLUDE_PATTERNS


def ensure_local_git_excludes(
    repo_root: str | Path,
    patterns: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Add adapter scratch patterns to .git/info/exclude for this checkout only."""

    root = Path(repo_root)
    exclude_path = root / ".git" / "info" / "exclude"
    requested = patterns or LOCAL_ADAPTER_EXCLUDE_PATTERNS
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    lines = existing.splitlines()
    existing_patterns = {
        line.strip() for line in lines if line.strip() and not line.startswith("#")
    }
    added: list[str] = []
    for pattern in requested:
        if pattern not in existing_patterns:
            lines.append(pattern)
            existing_patterns.add(pattern)
            added.append(pattern)
    if added or not exclude_path.exists():
        exclude_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {
        "exclude_path": str(exclude_path),
        "patterns": list(requested),
        "added": added,
        "changed": bool(added),
        "local_only": True,
    }


def _normalize(path: str | Path) -> str:
    raw = str(path).replace("\\", "/").strip()
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def _matches_local_exclude(path: str) -> bool:
    return any(
        path == pattern.rstrip("/") or path.startswith(pattern)
        for pattern in LOCAL_ADAPTER_EXCLUDE_PATTERNS
    )


def _is_user_local_adapter_state(path_lower: str) -> bool:
    return (
        "/.dream-studio/adapters/" in path_lower
        or "/.dream-studio/worktrees/" in path_lower
        or "/.dream-studio/sessions/" in path_lower
    )
