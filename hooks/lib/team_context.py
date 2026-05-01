"""Team collaboration context loader.

Loads team-wide gotchas, conventions, and pack overrides from
.dream-studio/team/ when available. Falls back gracefully if files don't exist.

Public API
----------
load_team_gotchas() → list[dict] | None
    Load team gotchas.yml if it exists, return None otherwise.

load_team_conventions() → str | None
    Load team conventions.md if it exists, return None otherwise.

load_team_pack_overrides() → dict | None
    Load team pack-overrides.yml if it exists, return None otherwise.

Team file priority
------------------
When both team and personal files exist:
  1. Team gotchas load FIRST (organization-wide anti-patterns)
  2. Personal/skill-specific gotchas load SECOND (individual overrides)

This ensures team standards are always visible while allowing individual
customization.

Directory structure
-------------------
.dream-studio/team/
  ├── gotchas.yml          — team anti-patterns
  ├── conventions.md       — coding standards
  └── pack-overrides.yml   — pack config overrides
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Import paths - handle both module and script contexts
try:
    from . import paths
except ImportError:
    import sys as _sys
    _lib_path = Path(__file__).parent
    if str(_lib_path) not in _sys.path:
        _sys.path.insert(0, str(_lib_path))
    import paths  # type: ignore[import-not-found]


def _team_dir() -> Path | None:
    """Return the .dream-studio/team directory if it exists, else None.

    Team files are project-specific (committed to git), so we look in the
    project root's .dream-studio/team/, not the user's home directory.
    """
    try:
        # Look in project root, not user data directory
        team = paths.project_root() / ".dream-studio" / "team"
        return team if team.is_dir() else None
    except Exception:
        return None


def _parse_yaml_simple(text: str) -> dict[str, Any] | None:
    """Parse YAML using minimal fallback parser (no PyYAML dependency).

    Same logic as gotcha_scanner._parse_yaml_block — handles flat list-of-mappings.
    """
    try:
        import yaml  # type: ignore[import-untyped]
        return yaml.safe_load(text)  # type: ignore[no-any-return]
    except ImportError:
        pass

    # Minimal fallback parser
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


def load_team_gotchas() -> list[dict] | None:
    """Load team gotchas.yml and return a flat list of entry dicts.

    Returns None if the file doesn't exist or can't be parsed.

    Each dict has the same shape as gotcha_scanner entries:
        skill       str   always "team" for team gotchas
        id          str   entry id
        severity    str   "critical" | "high" | "medium" | "low" | ""
        title       str
        context     str
        fix         str
        discovered  str   ISO date or ""
        section     str   "avoid" | "best_practices" | "edge_cases" | ...
    """
    team = _team_dir()
    if not team:
        return None

    gotchas_path = team / "gotchas.yml"
    if not gotchas_path.is_file():
        return None

    try:
        raw = gotchas_path.read_text(encoding="utf-8")
    except OSError:
        return None

    data = _parse_yaml_simple(raw)
    if not isinstance(data, dict):
        return None

    entries: list[dict] = []
    for section, items in data.items():
        if section == "version" or not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            entry: dict[str, str] = {
                "skill": "team",  # Special marker for team-wide gotchas
                "section": section,
                "id": str(item.get("id", "")),
                "severity": str(item.get("severity", "")),
                "title": str(item.get("title", "")),
                "context": str(item.get("context", "")),
                "fix": str(item.get("fix", "")),
                "avoid": str(item.get("fix", "")),  # Map fix → avoid for formatter
                "discovered": str(item.get("discovered", "")),
            }
            entries.append(entry)
    return entries if entries else None


def load_team_conventions() -> str | None:
    """Load team conventions.md and return the raw markdown text.

    Returns None if the file doesn't exist.
    """
    team = _team_dir()
    if not team:
        return None

    conventions_path = team / "conventions.md"
    if not conventions_path.is_file():
        return None

    try:
        return conventions_path.read_text(encoding="utf-8")
    except OSError:
        return None


def load_team_pack_overrides() -> dict[str, Any] | None:
    """Load team pack-overrides.yml and return the parsed dict.

    Returns None if the file doesn't exist or can't be parsed.
    """
    team = _team_dir()
    if not team:
        return None

    overrides_path = team / "pack-overrides.yml"
    if not overrides_path.is_file():
        return None

    try:
        raw = overrides_path.read_text(encoding="utf-8")
    except OSError:
        return None

    return _parse_yaml_simple(raw)
