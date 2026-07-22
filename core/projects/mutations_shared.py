"""Shared helpers for project lifecycle mutations.

WO-GF-CORE-DATA-split: split from core/projects/mutations.py into
mutations_{shared,activation,delete,register,metadata}.py; core/projects/
mutations.py is now a thin facade re-exporting the public API.
"""

from __future__ import annotations

from pathlib import Path


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    # Lazy import via ds.py — see core.projects.queries._require_db for rationale.
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")
    return paths.sqlite_path
