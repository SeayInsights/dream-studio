"""gotcha_scanner.py — Scan and search gotchas.yml files across all dream-studio skills.

Indexes gotcha entries by skill, mode, and keyword.  Provides four public
functions that are safe to call repeatedly within the same process: scan
results are cached in a module-level dict after the first load.

Gotchas live in two locations (relative to plugin root):
    skills/<skill>/gotchas.yml
    skills/<skill>/modes/<mode>/gotchas.yml

Each file uses this YAML schema::

    version: 1.0
    avoid:
      - id: some-id
        severity: critical
        discovered: 2026-04-29
        title: "Never do X"
        context: "Because Y"
        fix: "Do Z instead"
    best_practices:
      - ...
    edge_cases:
      - ...
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# YAML loading — prefer PyYAML; fall back to a minimal line-by-line parser
# ---------------------------------------------------------------------------

try:
    import yaml as _yaml  # type: ignore

    def _load_yaml(text: str) -> dict:
        return _yaml.safe_load(text) or {}

except ImportError:
    _yaml = None  # type: ignore

    def _load_yaml(text: str) -> dict:  # type: ignore[misc]
        """Minimal regex-based parser for the known gotchas.yml structure.

        Only handles the flat list-of-mappings shape used in gotchas files.
        Does NOT support arbitrary YAML — just what we need here.
        """
        result: dict = {}
        current_category: str | None = None
        current_entry: dict | None = None
        current_key: str | None = None
        multiline_buffer: list[str] = []

        def _flush_multiline() -> None:
            nonlocal current_key, multiline_buffer
            if current_entry is not None and current_key and multiline_buffer:
                current_entry[current_key] = " ".join(
                    line.strip() for line in multiline_buffer if line.strip()
                )
            current_key = None
            multiline_buffer = []

        def _flush_entry() -> None:
            nonlocal current_entry
            _flush_multiline()
            if current_category and current_entry:
                result.setdefault(current_category, []).append(current_entry)
            current_entry = None

        for raw_line in text.splitlines():
            # --- top-level category keys (e.g. "avoid:", "best_practices:") ---
            top_match = re.match(r'^([a-z_]+)\s*:\s*$', raw_line)
            if top_match:
                _flush_entry()
                current_category = top_match.group(1)
                continue

            # --- list item start: "  - id: something" ---
            id_match = re.match(r'^\s+-\s+id:\s+(.+)$', raw_line)
            if id_match:
                _flush_entry()
                current_entry = {"id": id_match.group(1).strip().strip('"').strip("'")}
                continue

            # --- scalar key-value inside an entry: "    key: value" ---
            kv_match = re.match(r'^\s+([a-z_]+):\s+(.+)$', raw_line)
            if kv_match and current_entry is not None:
                _flush_multiline()
                key = kv_match.group(1)
                val = kv_match.group(2).strip().strip('"').strip("'")
                current_entry[key] = val
                continue

            # --- block scalar or continuation line ---
            if current_entry is not None and raw_line.strip():
                if current_key is None:
                    # bare continuation — try to detect key
                    bare_key = re.match(r'^\s+([a-z_]+):\s*$', raw_line)
                    if bare_key:
                        _flush_multiline()
                        current_key = bare_key.group(1)
                    else:
                        multiline_buffer.append(raw_line)
                else:
                    multiline_buffer.append(raw_line)

        _flush_entry()
        return result


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_CACHE: list[dict] | None = None
_CACHE_ROOT: Path | None = None  # root that was scanned


def clear_cache() -> None:
    """Invalidate the module-level scan cache so the next call re-reads disk."""
    global _CACHE, _CACHE_ROOT
    _CACHE = None
    _CACHE_ROOT = None


# ---------------------------------------------------------------------------
# Severity ordering for sorting
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _severity_rank(entry: dict) -> int:
    return _SEVERITY_ORDER.get(str(entry.get("severity", "low")).lower(), 4)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_root(plugin_root: Path | None) -> Path:
    if plugin_root is not None:
        return plugin_root
    from . import paths
    return paths.plugin_root()


def _parse_gotchas_file(
    file_path: Path,
    skill: str,
    mode: str | None,
    plugin_root: Path,
) -> list[dict]:
    """Parse a single gotchas.yml and return normalised entry dicts."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return []

    try:
        data = _load_yaml(text)
    except Exception:
        return []

    if not isinstance(data, dict):
        return []

    # Relative source path for traceability
    try:
        source_file = str(file_path.relative_to(plugin_root)).replace("\\", "/")
    except ValueError:
        source_file = str(file_path).replace("\\", "/")

    entries: list[dict] = []
    for category in ("avoid", "best_practices", "edge_cases"):
        raw_list = data.get(category)
        if not isinstance(raw_list, list):
            continue
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            entries.append(
                {
                    "id": str(raw.get("id", "")).strip() or "(no-id)",
                    "skill": skill,
                    "mode": mode,
                    "severity": str(raw.get("severity", "low")).lower(),
                    "category": category,
                    "title": str(raw.get("title", "")).strip(),
                    "context": str(raw.get("context", "")).strip(),
                    "fix": str(raw.get("fix", "")).strip() or None,
                    "discovered": str(raw.get("discovered", "")).strip() or None,
                    "source_file": source_file,
                }
            )
    return entries


def _file_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_all_gotchas(plugin_root: Path | None = None) -> list[dict]:
    """Scan every gotchas.yml file in the plugin tree and return a flat list.

    Results are cached for the lifetime of the process (or until
    :func:`clear_cache` is called).  Pass an explicit *plugin_root* to scan a
    different location; this also busts the cache if the root changes.

    Returns a list of dicts with keys:
        id, skill, mode, severity, category, title, context, fix, source_file
    """
    global _CACHE, _CACHE_ROOT

    root = _resolve_root(plugin_root)

    if _CACHE is not None and _CACHE_ROOT == root:
        return _CACHE

    skills_dir = root / "skills"
    all_entries: list[dict] = []

    if not skills_dir.is_dir():
        _CACHE = all_entries
        _CACHE_ROOT = root
        return _CACHE

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_name = skill_dir.name

        # Skill-level gotchas
        skill_gotchas = skill_dir / "gotchas.yml"
        if skill_gotchas.is_file():
            all_entries.extend(_parse_gotchas_file(skill_gotchas, skill_name, None, root))

        # Mode-level gotchas
        modes_dir = skill_dir / "modes"
        if modes_dir.is_dir():
            for mode_dir in sorted(modes_dir.iterdir()):
                if not mode_dir.is_dir():
                    continue
                mode_name = mode_dir.name
                mode_gotchas = mode_dir / "gotchas.yml"
                if mode_gotchas.is_file():
                    all_entries.extend(
                        _parse_gotchas_file(mode_gotchas, skill_name, mode_name, root)
                    )

    _CACHE = all_entries
    _CACHE_ROOT = root
    return _CACHE


def search_gotchas(query: str, plugin_root: Path | None = None) -> list[dict]:
    """Return gotchas whose title, context, or fix contain any query token.

    The *query* string is split on whitespace; an entry matches if **any**
    token appears (case-insensitively) in the entry's searchable text.
    Results are sorted by severity (critical → high → medium → low).

    Example::

        results = search_gotchas("database migration")
        # returns entries mentioning "database", "migration", or related keywords
    """
    tokens = [t.lower() for t in query.split() if t]
    if not tokens:
        return []

    all_entries = scan_all_gotchas(plugin_root)
    matched: list[dict] = []

    for entry in all_entries:
        haystack = " ".join(
            [
                entry.get("title", ""),
                entry.get("context", ""),
                entry.get("fix", "") or "",
            ]
        ).lower()

        if any(tok in haystack for tok in tokens):
            matched.append(entry)

    matched.sort(key=_severity_rank)
    return matched


def get_recent_gotchas(
    skill: Optional[str] = None,
    limit: int = 3,
    plugin_root: Optional[Path] = None,
) -> list[dict]:
    """Return the *limit* most recently added gotchas.

    Recency is determined by the ``discovered`` date field (ISO 8601) when
    present; entries without a date fall back to the source file's mtime and
    sort after dated entries.  Optionally filter to a single *skill*.
    """
    root = _resolve_root(plugin_root)
    all_entries = scan_all_gotchas(root)

    if skill is not None:
        all_entries = [e for e in all_entries if e.get("skill") == skill]

    def _sort_key(e: dict) -> tuple:
        """Return a key that sorts newest-first.

        Dated entries (tier 0) come before mtime-only entries (tier 1).
        Within each tier we negate so that ``sorted(..., reverse=False)``
        produces descending order without reversing the tier ordering.
        """
        discovered = e.get("discovered") or ""
        if discovered:
            # Negate ISO date string by inverting each character code so that
            # a later date (larger string) maps to a smaller key.
            negated = "".join(chr(0x10FFFF - ord(c)) for c in discovered)
            return (0, negated)
        # Fall back to file mtime — negate so larger mtime → smaller key
        src = e.get("source_file", "")
        try:
            mtime = _file_mtime(root / src)
        except Exception:
            mtime = 0.0
        return (1, str(-mtime).zfill(25))

    all_entries = sorted(all_entries, key=_sort_key)
    return all_entries[:limit]


def get_gotchas_for_skill(skill: str, plugin_root: Optional[Path] = None) -> list[dict]:
    """Return all gotchas belonging to *skill* (including all of its modes).

    Results preserve the on-disk order (avoid → best_practices → edge_cases,
    skill-level before mode-level).
    """
    all_entries = scan_all_gotchas(plugin_root)
    return [e for e in all_entries if e.get("skill") == skill]
