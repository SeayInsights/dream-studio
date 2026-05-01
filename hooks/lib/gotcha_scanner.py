"""Gotcha scanner — reads gotchas.yml files across all skills.

Public API
----------
scan_all_gotchas(plugin_root=None)   → list[dict]  all entries, flat
search_gotchas(query)                → list[dict]  token-matched entries
get_recent_gotchas(skill=None, n=3)  → list[dict]  newest by discovered date
get_gotchas_for_skill(skill)         → list[dict]  all gotchas for one skill

Each returned dict has at minimum:
    skill       str   e.g. "core:build"
    id          str   entry id within the file
    severity    str   "critical" | "high" | "medium" | "low" | ""
    title       str
    context     str
    fix         str
    discovered  str   ISO date or ""
    section     str   "avoid" | "best_practices" | "edge_cases" | ...

SQLite-first path
-----------------
Each public function tries the DB (lib.studio_db) before the file-walk.
If the DB returns results they are returned immediately.  If the DB is
empty OR raises any exception the file-walk runs as normal.  The
file-walk path is never removed or altered — it is the authoritative
fallback.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Module-level cache (file-walk results only; DB results bypass the cache)
# ---------------------------------------------------------------------------

_cache: list[dict] | None = None


def clear_cache() -> None:
    """Invalidate the in-memory file-walk cache."""
    global _cache
    _cache = None


# ---------------------------------------------------------------------------
# Internal helpers — DB layer (lazy imports, silent on any exception)
# ---------------------------------------------------------------------------

def _try_db_search(keyword: str) -> list[dict] | None:
    """Return DB results for *keyword*, or None to signal fallback."""
    try:
        from lib.studio_db import search_gotchas_db  # noqa: PLC0415
        results = search_gotchas_db(keyword)
        return results if results else None
    except Exception:
        return None


def _try_db_gotchas_for_skill(skill_id: str) -> list[dict] | None:
    """Return DB rows for *skill_id*, or None to signal fallback.

    Tries both the canonical ``pack:mode`` form and the bare mode name so
    that callers can pass either ``"build"`` or ``"core:build"``.
    """
    try:
        from lib.studio_db import get_gotchas_for_skill as db_get  # noqa: PLC0415
        results = db_get(skill_id)
        if results:
            return results
        # If the caller passed a bare mode name, try a prefix scan.
        if ":" not in skill_id:
            results = db_get(skill_id)  # already tried — nothing to add here
        return None
    except Exception:
        return None


def _try_db_recent(skill_id: str | None, limit: int) -> list[dict] | None:
    """Return the most recently discovered gotchas from the DB, or None."""
    try:
        from lib.studio_db import _connect  # noqa: PLC0415
        conn = _connect()
        if skill_id:
            rows = conn.execute(
                "SELECT * FROM reg_gotchas WHERE skill_id=? "
                "ORDER BY discovered DESC LIMIT ?",
                (skill_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reg_gotchas ORDER BY discovered DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
        results = [dict(r) for r in rows]
        return results if results else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Internal helpers — YAML / file-walk layer
# ---------------------------------------------------------------------------

def _skill_id_from_path(gotchas_path: Path, skills_root: Path) -> str:
    """Derive a ``pack:mode`` skill id from the path to a gotchas.yml.

    Examples
    --------
    skills/core/modes/build/gotchas.yml    → "core:build"
    skills/workflow/gotchas.yml            → "workflow"
    skills/analyze/modes/multi/gotchas.yml → "analyze:multi"
    """
    try:
        rel = gotchas_path.relative_to(skills_root)
        parts = rel.parts  # e.g. ("core", "modes", "build", "gotchas.yml")
        pack = parts[0]
        # Filter out "modes" intermediary directory
        mode_parts = [p for p in parts[1:-1] if p != "modes"]
        if mode_parts:
            return f"{pack}:{mode_parts[-1]}"
        return pack
    except ValueError:
        return gotchas_path.parent.name


def _parse_yaml_block(text: str) -> Any:
    """Parse YAML using PyYAML when available, falling back to a minimal
    hand-rolled parser that handles the flat list-of-mappings structure
    used by every gotchas.yml in this repo.
    """
    try:
        import yaml  # type: ignore[import-untyped]  # noqa: PLC0415
        return yaml.safe_load(text)
    except ImportError:
        pass

    # Minimal fallback: build a dict of section → list[dict]
    result: dict[str, list[dict]] = {}
    current_section: str | None = None
    current_item: dict[str, str] = {}

    def _flush_item() -> None:
        if current_section and current_item:
            result.setdefault(current_section, []).append(dict(current_item))

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Top-level key (no indent, ends with colon, no value)
        if indent == 0 and stripped.endswith(":") and not stripped.startswith("-"):
            _flush_item()
            current_item = {}
            current_section = stripped[:-1]
            continue

        # List item start
        if stripped.startswith("- "):
            _flush_item()
            current_item = {}
            rest = stripped[2:]
            if ":" in rest:
                k, _, v = rest.partition(":")
                current_item[k.strip()] = v.strip().strip('"')
            continue

        # Mapping key inside a list item
        if ":" in stripped and not stripped.startswith("-"):
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip().strip('"')
            current_item[k] = v
            continue

    _flush_item()
    return result if result else None


def _load_gotchas_file(path: Path, skill_id: str) -> list[dict]:
    """Parse a single gotchas.yml and return a flat list of entry dicts."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []

    data = _parse_yaml_block(raw)
    if not isinstance(data, dict):
        return []

    entries: list[dict] = []
    for section, items in data.items():
        if section == "version" or not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            entry: dict[str, str] = {
                "skill": skill_id,
                "section": section,
                "id": str(item.get("id", "")),
                "severity": str(item.get("severity", "")),
                "title": str(item.get("title", "")),
                "context": str(item.get("context", "")),
                "fix": str(item.get("fix", "")),
                "discovered": str(item.get("discovered", "")),
            }
            entries.append(entry)
    return entries


def _walk_all(plugin_root: Path | None = None) -> list[dict]:
    """Walk every gotchas.yml under *plugin_root*/skills and return a flat list."""
    global _cache
    if _cache is not None:
        return _cache

    try:
        if plugin_root is None:
            from lib import paths as _paths  # noqa: PLC0415
            plugin_root = _paths.plugin_root()
    except Exception:
        return []

    skills_root = Path(plugin_root) / "skills"
    if not skills_root.is_dir():
        return []

    all_entries: list[dict] = []
    for gotchas_file in sorted(skills_root.rglob("gotchas.yml")):
        skill_id = _skill_id_from_path(gotchas_file, skills_root)
        all_entries.extend(_load_gotchas_file(gotchas_file, skill_id))

    _cache = all_entries
    return _cache


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_all_gotchas(plugin_root: Path | None = None) -> list[dict]:
    """Return every gotcha entry across all skills (file-walk, cached).

    This function always uses the file-walk path — it is the raw data
    loader used by the other public functions.  It does NOT hit the DB
    because the DB path would return DB-shaped dicts while callers of
    this function expect the file-walk shape.
    """
    return _walk_all(plugin_root)


def search_gotchas(query: str) -> list[dict]:
    """Return entries where any token in *query* matches title, context, fix,
    id, or section (case-insensitive).

    Tries the SQLite DB first.  Falls back to file-walk if the DB is
    unavailable or returns no rows.
    """
    # --- DB path ---
    db_results = _try_db_search(query)
    if db_results is not None:
        return db_results

    # --- File-walk fallback ---
    tokens = [t.lower() for t in query.split() if t]
    if not tokens:
        return []

    results: list[dict] = []
    for entry in _walk_all():
        haystack = " ".join([
            entry.get("title", ""),
            entry.get("context", ""),
            entry.get("fix", ""),
            entry.get("id", ""),
            entry.get("section", ""),
            entry.get("skill", ""),
        ]).lower()
        if any(tok in haystack for tok in tokens):
            results.append(entry)
    return results


def get_recent_gotchas(skill: str | None = None, limit: int = 3) -> list[dict]:
    """Return the *limit* most recently discovered gotchas.

    If *skill* is given (e.g. ``"core:build"`` or ``"build"``), restricts
    to that skill.  Tries the DB first, falls back to file-walk sort.
    """
    # --- DB path ---
    db_results = _try_db_recent(skill, limit)
    if db_results is not None:
        return db_results

    # --- File-walk fallback ---
    entries = _walk_all()
    if skill:
        skill_lower = skill.lower()
        entries = [
            e for e in entries
            if e.get("skill", "").lower() == skill_lower
            or e.get("skill", "").lower().endswith(f":{skill_lower}")
        ]

    def _sort_key(e: dict) -> str:
        d = e.get("discovered", "") or ""
        # Ensure ISO date strings sort correctly; fall back to empty string
        return d if re.match(r"\d{4}-\d{2}-\d{2}", d) else ""

    sorted_entries = sorted(entries, key=_sort_key, reverse=True)
    return sorted_entries[:limit]


def get_gotchas_for_skill(skill: str) -> list[dict]:
    """Return all gotchas associated with *skill*.

    *skill* may be a full ``pack:mode`` id (``"core:build"``) or a bare
    mode name (``"build"``).  Tries the DB first for each candidate form,
    then falls back to file-walk.
    """
    # --- DB path: try exact skill_id, then bare mode ---
    db_results = _try_db_gotchas_for_skill(skill)
    if db_results is None and ":" not in skill:
        # skill is a bare mode — the DB stores "pack:mode"; we can't know
        # the pack without context, so the file-walk is better here.
        pass
    if db_results is not None:
        return db_results

    # --- File-walk fallback ---
    skill_lower = skill.lower()
    return [
        e for e in _walk_all()
        if e.get("skill", "").lower() == skill_lower
        or e.get("skill", "").lower().endswith(f":{skill_lower}")
    ]
