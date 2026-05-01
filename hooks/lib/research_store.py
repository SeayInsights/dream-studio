"""Persistent research cache read/write/query interface.

Research entries are stored as JSON files under ``~/.dream-studio/research/``.
Each file represents one topic and follows this schema::

    {
        "topic": str,
        "sources": [
            {
                "url": str,
                "tier": str,
                "date": str,
                "key_findings": str | list[str]
            },
            ...
        ],
        "confidence": float | str,
        "triangulated": bool,
        "refresh_due": str,   # ISO date, e.g. "2026-06-01"
        "saved_date": str     # ISO date, e.g. "2026-05-01"
    }

Topic names are sanitised before use as filenames: lowercased, spaces and
forward-slashes replaced with hyphens, and only safe characters retained.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from . import paths


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _research_dir() -> Path:
    """Return ``~/.dream-studio/research/``, creating it if absent."""
    d = paths.user_data_dir() / "research"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sanitize_topic(topic: str) -> str:
    """Convert a topic string to a safe, lowercase filename stem.

    Spaces and forward-slashes become hyphens; any remaining character that
    is not alphanumeric, a hyphen, or an underscore is dropped; leading and
    trailing hyphens are stripped.
    """
    slug = topic.lower()
    slug = slug.replace(" ", "-").replace("/", "-")
    slug = re.sub(r"[^a-z0-9_-]", "", slug)
    slug = slug.strip("-")
    return slug or "untitled"


def _topic_path(topic: str) -> Path:
    return _research_dir() / f"{_sanitize_topic(topic)}.json"


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """Write *payload* as JSON to *path* atomically via temp-file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_file(path: Path) -> dict[str, Any] | None:
    """Read and parse a research JSON file, returning None on any error."""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_research(topic: str, data: dict[str, Any]) -> Path:
    """Save *data* to the research cache for *topic*.

    The *data* dict is stored verbatim (the caller is responsible for
    populating required fields). The file is written atomically so a crash
    mid-write never leaves a corrupt entry. If an entry for *topic* already
    exists it is overwritten.

    Returns the Path of the written file.
    """
    path = _topic_path(topic)
    _atomic_write(path, data)
    return path


def get_research(topic: str) -> dict[str, Any] | None:
    """Return cached research for *topic*, or ``None`` if not found."""
    path = _topic_path(topic)
    if not path.is_file():
        return None
    return _load_file(path)


def is_stale(topic: str) -> bool:
    """Return ``True`` if the cached research for *topic* needs refreshing.

    Staleness is determined by comparing today's date against the
    ``refresh_due`` field (ISO date string).  Returns ``True`` when:

    * the topic is not cached,
    * ``refresh_due`` is missing or unparseable, or
    * ``refresh_due`` is today or in the past.
    """
    doc = get_research(topic)
    if doc is None:
        return True
    refresh_due_raw = doc.get("refresh_due")
    if not refresh_due_raw:
        return True
    try:
        refresh_due = date.fromisoformat(str(refresh_due_raw))
    except ValueError:
        return True
    return date.today() >= refresh_due


def list_topics() -> list[dict[str, Any]]:
    """Return summary metadata for every cached research topic.

    Each entry in the returned list has the shape::

        {
            "topic": str,
            "confidence": <value from doc or None>,
            "triangulated": <value from doc or False>,
            "refresh_due": <value from doc or None>,
            "stale": bool
        }

    Topics whose cache files cannot be read are silently skipped.
    """
    results: list[dict[str, Any]] = []
    research_dir = _research_dir()
    for path in sorted(research_dir.glob("*.json")):
        doc = _load_file(path)
        if doc is None:
            continue
        topic = doc.get("topic", path.stem)
        refresh_due = doc.get("refresh_due")
        stale: bool
        if not refresh_due:
            stale = True
        else:
            try:
                stale = date.today() >= date.fromisoformat(str(refresh_due))
            except ValueError:
                stale = True
        results.append(
            {
                "topic": topic,
                "confidence": doc.get("confidence"),
                "triangulated": doc.get("triangulated", False),
                "refresh_due": refresh_due,
                "stale": stale,
            }
        )
    return results


def delete_research(topic: str) -> bool:
    """Remove the cache file for *topic*.

    Returns ``True`` if the file existed and was deleted, ``False`` if it
    was not found.
    """
    path = _topic_path(topic)
    if not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def search_research(keyword: str) -> list[dict[str, Any]]:
    """Return all cached research entries that contain *keyword*.

    Matching is case-insensitive and checks:

    * the ``topic`` field of the stored document,
    * the ``key_findings`` field of every source (string or list of strings).

    Returns a list of full research documents (same shape as ``get_research``).
    """
    needle = keyword.lower()
    matches: list[dict[str, Any]] = []
    research_dir = _research_dir()
    for path in sorted(research_dir.glob("*.json")):
        doc = _load_file(path)
        if doc is None:
            continue

        # Check topic name
        topic_val = str(doc.get("topic", path.stem)).lower()
        if needle in topic_val:
            matches.append(doc)
            continue

        # Check key_findings across all sources
        found = False
        for source in doc.get("sources", []):
            kf = source.get("key_findings", "")
            if isinstance(kf, list):
                if any(needle in str(item).lower() for item in kf):
                    found = True
                    break
            else:
                if needle in str(kf).lower():
                    found = True
                    break
        if found:
            matches.append(doc)

    return matches
