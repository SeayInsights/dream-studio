"""session_parser — parse .sessions/YYYY-MM-DD/handoff-*.json and recap-*.md files.

Public API:
    parse_handoff(path)        → dict with standardised handoff fields
    parse_recap(path)          → dict with standardised recap fields
    scan_sessions(root, days)  → list[dict] sorted by date descending
    extract_blockers(sessions) → list[dict] with frequency-ranked blockers
"""

from __future__ import annotations

import json
import re
import sys
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _dir_date(path: Path) -> str:
    """Extract YYYY-MM-DD from the parent directory name, or empty string."""
    parent = path.parent.name
    if _DATE_RE.match(parent):
        return parent
    return ""


def _infer_skills(phase: str, topic: str) -> list[str]:
    """Infer likely skills used from pipeline_phase and topic keywords."""
    skills: list[str] = []
    phase_map = {
        "think": ["dream-studio:core"],
        "plan": ["dream-studio:core"],
        "build": ["dream-studio:core"],
        "review": ["dream-studio:core"],
        "verify": ["dream-studio:core"],
        "ship": ["dream-studio:core"],
        "handoff": ["dream-studio:core"],
        "recap": ["dream-studio:core"],
        "complete": ["dream-studio:core"],
        "debug": ["dream-studio:quality"],
        "polish": ["dream-studio:quality"],
        "harden": ["dream-studio:quality"],
        "secure": ["dream-studio:quality"],
        "scan": ["dream-studio:security"],
        "dast": ["dream-studio:security"],
        "comply": ["dream-studio:security"],
        "design": ["dream-studio:domains"],
        "game": ["dream-studio:domains"],
        "saas": ["dream-studio:domains"],
        "mcp": ["dream-studio:domains"],
        "dashboard": ["dream-studio:domains"],
        "powerbi": ["dream-studio:domains"],
        "career": ["dream-studio:career"],
        "analyze": ["dream-studio:analyze"],
        "workflow": ["dream-studio:workflow"],
    }
    for key, mapped in phase_map.items():
        if key in phase.lower():
            skills.extend(mapped)
    topic_lower = topic.lower()
    for key, mapped in phase_map.items():
        if key in topic_lower and mapped not in skills:
            skills.extend(mapped)
    # deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for s in skills:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result or ["dream-studio:core"]


def _safe_list(value: Any) -> list[str]:
    """Return a list[str] from value; coerce or return empty list."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str) and value:
        return [value]
    return []


# ---------------------------------------------------------------------------
# Handoff JSON parser
# ---------------------------------------------------------------------------

def parse_handoff(path: Path) -> dict:
    """Parse a handoff JSON file into a standardised dict.

    Args:
        path: Absolute path to a ``handoff-*.json`` file.

    Returns:
        Dict with keys: type, date, topic, phase, tasks_completed,
        tasks_total, broken_items, corrections, skills_used, branch,
        next_action, raw.

    Raises:
        Nothing — malformed / missing files return a dict with defaults
        and a ``_parse_error`` key set to the exception message.
    """
    result: dict = {
        "type": "handoff",
        "date": _dir_date(path),
        "topic": "",
        "phase": "",
        "tasks_completed": 0,
        "tasks_total": 0,
        "broken_items": [],
        "corrections": [],
        "skills_used": [],
        "branch": "",
        "next_action": "",
        "raw": {},
    }
    try:
        text = path.read_text(encoding="utf-8")
        data: dict = json.loads(text)
    except FileNotFoundError as exc:
        result["_parse_error"] = f"file not found: {exc}"
        return result
    except json.JSONDecodeError as exc:
        result["_parse_error"] = f"JSON decode error: {exc}"
        return result
    except OSError as exc:
        result["_parse_error"] = f"OS error reading file: {exc}"
        return result

    result["raw"] = data

    # date — prefer explicit field, fall back to directory name
    result["date"] = str(data.get("date", "") or result["date"])

    result["topic"] = str(data.get("topic", "") or "")
    result["phase"] = str(data.get("pipeline_phase", "") or "")
    result["tasks_completed"] = int(data.get("tasks_completed", 0) or 0)
    result["tasks_total"] = int(data.get("tasks_total", 0) or 0)
    result["branch"] = str(data.get("branch", "") or "")
    result["next_action"] = str(data.get("next_action", "") or "")

    # broken_items — from "broken" array (list of strings or dicts)
    broken_raw = data.get("broken", [])
    if isinstance(broken_raw, list):
        broken_items: list[str] = []
        for item in broken_raw:
            if isinstance(item, str):
                broken_items.append(item)
            elif isinstance(item, dict):
                # attempt to get a meaningful string from the dict
                for key in ("description", "item", "issue", "message", "text"):
                    if key in item:
                        broken_items.append(str(item[key]))
                        break
                else:
                    broken_items.append(str(item))
        result["broken_items"] = broken_items
    else:
        result["broken_items"] = []

    # corrections — from "lessons_this_session" (may not exist in older files)
    lessons_raw = data.get("lessons_this_session", [])
    result["corrections"] = _safe_list(lessons_raw)

    # skills_used — inferred from phase + topic
    result["skills_used"] = _infer_skills(result["phase"], result["topic"])

    return result


# ---------------------------------------------------------------------------
# Recap Markdown parser
# ---------------------------------------------------------------------------

# Matches section headers like "## Section Name"
_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_DATE_LINE_RE = re.compile(r"^Date:\s*(.+)$", re.MULTILINE)
_HEADING_RE = re.compile(r"^#\s+Recap:\s*(.+)$", re.MULTILINE)
_CORRECTION_RE = re.compile(r"Director correction", re.IGNORECASE)
_LIST_ITEM_RE = re.compile(r"^[-*]\s+(.+)$")


def _extract_section(text: str, section_name: str) -> str:
    """Return the raw text between ``## section_name`` and the next ``##`` (or EOF)."""
    pattern = re.compile(
        r"^##\s+" + re.escape(section_name) + r"\s*$(.+?)(?=^##|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return ""
    return match.group(1)


def _parse_list_items(block: str) -> list[str]:
    """Extract bullet-point items from a markdown block."""
    items: list[str] = []
    for line in block.splitlines():
        m = _LIST_ITEM_RE.match(line.strip())
        if m:
            items.append(m.group(1).strip())
    return items


def _extract_plain_text(block: str) -> str:
    """Return the first non-empty, non-bullet line from a block as plain text."""
    for line in block.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            # Remove leading bullet if present
            m = _LIST_ITEM_RE.match(stripped)
            return m.group(1).strip() if m else stripped
    return ""


def parse_recap(path: Path) -> dict:
    """Parse a recap markdown file into a standardised dict.

    Args:
        path: Absolute path to a ``recap-*.md`` file.

    Returns:
        Dict with keys: type, date, topic, what_built, decisions,
        risk_flags, remaining, next_step, corrections.

    Raises:
        Nothing — malformed / missing files return defaults and set
        ``_parse_error``.
    """
    result: dict = {
        "type": "recap",
        "date": _dir_date(path),
        "topic": "",
        "what_built": [],
        "decisions": [],
        "risk_flags": [],
        "remaining": [],
        "next_step": "",
        "corrections": [],
    }
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        result["_parse_error"] = f"file not found: {exc}"
        return result
    except OSError as exc:
        result["_parse_error"] = f"OS error reading file: {exc}"
        return result

    # date — from "Date:" line, fall back to dir name
    date_match = _DATE_LINE_RE.search(text)
    if date_match:
        result["date"] = date_match.group(1).strip()

    # topic — from "# Recap: [topic]" heading
    heading_match = _HEADING_RE.search(text)
    if heading_match:
        result["topic"] = heading_match.group(1).strip()

    # Sections
    result["what_built"] = _parse_list_items(_extract_section(text, "What was built"))
    result["decisions"] = _parse_list_items(_extract_section(text, "Decisions"))
    result["risk_flags"] = _parse_list_items(_extract_section(text, "Risk flags"))
    result["remaining"] = _parse_list_items(_extract_section(text, "Remaining work"))

    # next_step — "## Next step" section, first meaningful line
    next_block = _extract_section(text, "Next step")
    result["next_step"] = _extract_plain_text(next_block)

    # corrections — lines mentioning "Director correction"
    corrections: list[str] = []
    for line in text.splitlines():
        if _CORRECTION_RE.search(line):
            stripped = line.strip()
            if stripped:
                corrections.append(stripped)
    result["corrections"] = corrections

    return result


# ---------------------------------------------------------------------------
# Session scanner
# ---------------------------------------------------------------------------

def scan_sessions(root: Path, days: int = 90) -> list[dict]:
    """Scan a ``.sessions/`` directory tree, returning parsed sessions.

    Args:
        root: Path to the ``.sessions/`` directory.
        days: Only include sessions from the last N days (default 90).

    Returns:
        List of parsed dicts (handoff + recap), sorted by date descending.
        Files that fail to parse are skipped with a stderr warning.
    """
    cutoff: date = date.today() - timedelta(days=days)
    sessions: list[dict] = []

    if not root.is_dir():
        warnings.warn(f"scan_sessions: root is not a directory: {root}", stacklevel=2)
        return sessions

    for date_dir in sorted(root.iterdir()):
        if not date_dir.is_dir():
            continue
        dir_name = date_dir.name
        if not _DATE_RE.match(dir_name):
            continue
        try:
            dir_date = date.fromisoformat(dir_name)
        except ValueError:
            continue
        if dir_date < cutoff:
            continue

        for child in date_dir.iterdir():
            if not child.is_file():
                continue
            try:
                if child.name.startswith("handoff-") and child.suffix == ".json":
                    parsed = parse_handoff(child)
                    if "_parse_error" in parsed:
                        print(
                            f"[session_parser] WARNING: skipping {child}: {parsed['_parse_error']}",
                            file=sys.stderr,
                        )
                        continue
                    sessions.append(parsed)
                elif child.name.startswith("recap-") and child.suffix == ".md":
                    parsed = parse_recap(child)
                    if "_parse_error" in parsed:
                        print(
                            f"[session_parser] WARNING: skipping {child}: {parsed['_parse_error']}",
                            file=sys.stderr,
                        )
                        continue
                    sessions.append(parsed)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[session_parser] WARNING: unexpected error parsing {child}: {exc}",
                    file=sys.stderr,
                )

    # Sort by date descending (most recent first)
    def _sort_key(s: dict) -> str:
        return s.get("date", "") or ""

    sessions.sort(key=_sort_key, reverse=True)
    return sessions


# ---------------------------------------------------------------------------
# Blocker extractor
# ---------------------------------------------------------------------------

def extract_blockers(sessions: list[dict]) -> list[dict]:
    """Extract broken_items and risk_flags from a list of parsed sessions.

    Args:
        sessions: List of dicts as returned by scan_sessions / parse_handoff /
                  parse_recap.

    Returns:
        List of dicts: ``{item, source_date, source_topic, frequency}``,
        sorted by frequency descending then item text ascending.
        Items that appear in multiple sessions are counted once per session.
    """
    # Map normalised item text → list of (source_date, source_topic) tuples
    from collections import defaultdict

    occurrences: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for session in sessions:
        src_date = session.get("date", "")
        src_topic = session.get("topic", "")

        blockers: list[str] = []
        if session.get("type") == "handoff":
            blockers = session.get("broken_items", [])
        elif session.get("type") == "recap":
            blockers = session.get("risk_flags", [])

        seen_in_session: set[str] = set()
        for raw_item in blockers:
            normalised = raw_item.strip()
            if not normalised:
                continue
            # Count each unique item once per session to calculate frequency
            if normalised not in seen_in_session:
                seen_in_session.add(normalised)
                occurrences[normalised].append((src_date, src_topic))

    results: list[dict] = []
    for item, sources in occurrences.items():
        # Use the most-recent source as the representative one
        sources_sorted = sorted(sources, key=lambda t: t[0], reverse=True)
        latest_date, latest_topic = sources_sorted[0]
        results.append(
            {
                "item": item,
                "source_date": latest_date,
                "source_topic": latest_topic,
                "frequency": len(sources),
            }
        )

    results.sort(key=lambda d: (-d["frequency"], d["item"]))
    return results
