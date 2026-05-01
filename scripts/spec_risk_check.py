"""spec_risk_check.py — Scan for relevant prior experience before writing a spec.

CLI:
    py scripts/spec_risk_check.py <topic> [--json]

Searches three sources for prior experience relevant to the topic:
  1. Gotchas scan     — relevant gotchas.yml entries across all skills
  2. Session history  — past handoff/recap sessions with matching topics
  3. Draft lessons    — ~/.dream-studio/meta/draft-lessons/*.md keyword matches

Outputs a formatted risk pre-population report (or JSON with --json).
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Reconfigure stdout to UTF-8 so box-drawing characters render on Windows.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Path setup — allow imports from hooks/lib
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_REPO_ROOT / "hooks"))

from lib.gotcha_scanner import search_gotchas  # noqa: E402
from lib.session_parser import scan_sessions   # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DRAFT_LESSONS_DIR = Path.home() / ".dream-studio" / "meta" / "draft-lessons"
SESSIONS_DIR = Path.home() / ".dream-studio" / ".sessions"

MAX_GOTCHAS = 5
MAX_SESSIONS = 3
MAX_LESSONS = 3


# ---------------------------------------------------------------------------
# Keyword helpers
# ---------------------------------------------------------------------------

def _keywords(topic: str) -> list[str]:
    """Split topic into lowercase keyword tokens (no dedup needed)."""
    return [w.lower() for w in topic.split() if w]


def _matches(text: str, tokens: list[str]) -> bool:
    """Return True if any token appears in text (case-insensitive)."""
    lower = text.lower()
    return any(tok in lower for tok in tokens)


# ---------------------------------------------------------------------------
# Source 1: Gotchas scan
# ---------------------------------------------------------------------------

def _scan_gotchas(topic: str) -> list[dict]:
    """Return up to MAX_GOTCHAS gotcha entries relevant to topic."""
    try:
        results = search_gotchas(topic)
    except Exception as exc:
        sys.stderr.write(f"[spec_risk_check] WARNING: gotcha scan failed: {exc}\n")
        results = []
    return results[:MAX_GOTCHAS]


# ---------------------------------------------------------------------------
# Source 2: Session history
# ---------------------------------------------------------------------------

def _scan_session_history(topic: str) -> list[dict]:
    """Return up to MAX_SESSIONS past sessions whose topic matches keywords."""
    tokens = _keywords(topic)
    if not tokens:
        return []

    try:
        sessions = scan_sessions(SESSIONS_DIR, days=180)
    except Exception as exc:
        sys.stderr.write(f"[spec_risk_check] WARNING: session scan failed: {exc}\n")
        sessions = []

    matched: list[dict] = []
    for session in sessions:
        session_topic = session.get("topic", "") or ""
        if _matches(session_topic, tokens):
            matched.append(session)
            if len(matched) >= MAX_SESSIONS:
                break

    return matched


# ---------------------------------------------------------------------------
# Source 3: Draft lessons
# ---------------------------------------------------------------------------

def _parse_lesson_meta(path: Path) -> dict:
    """Parse title, date, and content from a draft-lesson .md file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    title = ""
    title_match = re.search(r"^#\s+Draft Lesson:\s*(.+)", text, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()

    date = ""
    date_match = re.search(r"^Date:\s*(\S+)", text, re.MULTILINE)
    if date_match:
        date = date_match.group(1).strip()

    return {"title": title, "date": date, "content": text, "path": str(path)}


def _scan_draft_lessons(topic: str) -> list[dict]:
    """Return up to MAX_LESSONS draft lessons matching topic keywords."""
    tokens = _keywords(topic)
    if not tokens:
        return []

    if not DRAFT_LESSONS_DIR.is_dir():
        return []

    matched: list[dict] = []
    for lesson_path in sorted(DRAFT_LESSONS_DIR.glob("*.md")):
        meta = _parse_lesson_meta(lesson_path)
        if not meta:
            continue
        haystack = meta.get("title", "") + " " + meta.get("content", "")
        if _matches(haystack, tokens):
            matched.append(meta)
            if len(matched) >= MAX_LESSONS:
                break

    return matched


# ---------------------------------------------------------------------------
# Edge case derivation
# ---------------------------------------------------------------------------

def _derive_edge_cases(gotchas: list[dict]) -> list[str]:
    """Turn each gotcha title into a suggested edge case question."""
    edge_cases: list[str] = []
    for gotcha in gotchas:
        title = gotcha.get("title", "").strip()
        if not title:
            continue
        # Strip leading imperatives like "Never", "Always", "Do not", "Don't"
        cleaned = re.sub(
            r"^(Never|Always|Do not|Don't|Avoid|Make sure|Ensure)\s+",
            "",
            title,
            flags=re.IGNORECASE,
        ).strip()
        # Lowercase first char for readability in the question
        if cleaned:
            cleaned = cleaned[0].lower() + cleaned[1:]
        edge_cases.append(f"What happens if {cleaned}?")
    return edge_cases


# ---------------------------------------------------------------------------
# Formatters — text
# ---------------------------------------------------------------------------

_BORDER = "═" * 43


def _fmt_section_header(label: str, count: int) -> str:
    found_str = f"{count} found"
    return f"\n {label} ({found_str})\n {'─' * (len(label) + len(found_str) + 3)}"


def _fmt_gotcha(g: dict) -> str:
    severity = g.get("severity", "")
    gid = g.get("id", "")
    mode = g.get("mode") or g.get("skill") or ""
    title = g.get("title", "")
    context = g.get("context", "")

    mode_suffix = f" ({mode})" if mode else ""
    lines = [f" [{severity}] {gid}{mode_suffix}"]
    if title:
        lines.append(f'   "{title}"')
    if context:
        lines.append(f"   {context}")
    return "\n".join(lines)


def _fmt_session(s: dict) -> str:
    date = s.get("date", "")
    stype = s.get("type", "")
    topic = s.get("topic", "")

    header = f" {date} | {stype}: {topic}"
    lines = [header]

    if stype == "handoff":
        broken = s.get("broken_items", [])
        corrections = s.get("corrections", [])
        if broken:
            lines.append(f"   Broken: {broken[0]}")
        if corrections:
            lines.append(f"   Lesson: {corrections[0]}")
    elif stype == "recap":
        risk_flags = s.get("risk_flags", [])
        remaining = s.get("remaining", [])
        if risk_flags:
            lines.append(f"   Risk: {risk_flags[0]}")
        if remaining:
            lines.append(f"   Remaining: {remaining[0]}")

    return "\n".join(lines)


def _fmt_lesson(lesson: dict) -> str:
    title = lesson.get("title", "(untitled)")
    date = lesson.get("date", "")
    date_str = f" ({date})" if date else ""
    return f" {title}{date_str}"


def _format_text(topic: str, gotchas: list[dict], sessions: list[dict], lessons: list[dict]) -> str:
    edge_cases = _derive_edge_cases(gotchas)

    lines: list[str] = [
        _BORDER,
        f" RISK PRE-POPULATION REPORT: {topic}",
        _BORDER,
    ]

    # Gotchas
    lines.append(_fmt_section_header("RELEVANT GOTCHAS", len(gotchas)))
    if gotchas:
        for g in gotchas:
            lines.append(_fmt_gotcha(g))
    else:
        lines.append(" (none)")

    # Sessions
    lines.append(_fmt_section_header("PRIOR SESSION CONTEXT", len(sessions)))
    if sessions:
        for s in sessions:
            lines.append(_fmt_session(s))
    else:
        lines.append(" (none)")

    # Draft lessons
    lines.append(_fmt_section_header("RELATED DRAFT LESSONS", len(lessons)))
    if lessons:
        for lesson in lessons:
            lines.append(_fmt_lesson(lesson))
    else:
        lines.append(" (none)")

    # Edge cases
    lines.append("\n SUGGESTED EDGE CASES FOR SPEC")
    lines.append(" " + "─" * 30)
    if edge_cases:
        lines.append(" Based on the above, consider these edge cases:")
        for ec in edge_cases:
            lines.append(f" • {ec}")
    else:
        lines.append(" (no gotchas found — no edge cases derived)")

    lines.append("")
    lines.append(_BORDER)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Formatters — JSON
# ---------------------------------------------------------------------------

def _format_json(topic: str, gotchas: list[dict], sessions: list[dict], lessons: list[dict]) -> str:
    edge_cases = _derive_edge_cases(gotchas)

    # Slim down sessions for JSON output (drop raw field)
    slim_sessions = []
    for s in sessions:
        entry = {k: v for k, v in s.items() if k != "raw"}
        slim_sessions.append(entry)

    # Slim down lessons for JSON output (drop full content)
    slim_lessons = [
        {"title": le.get("title", ""), "date": le.get("date", ""), "path": le.get("path", "")}
        for le in lessons
    ]

    payload = {
        "topic": topic,
        "gotchas": gotchas,
        "sessions": slim_sessions,
        "draft_lessons": slim_lessons,
        "suggested_edge_cases": edge_cases,
    }
    return json.dumps(payload, indent=2, default=str)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="spec_risk_check",
        description="Scan for relevant prior experience before writing a spec.",
    )
    parser.add_argument("topic", help="Topic string to search for (e.g. 'database migration')")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output results as JSON instead of formatted text",
    )
    args = parser.parse_args()

    topic: str = args.topic.strip()
    if not topic:
        parser.error("topic must be a non-empty string")

    gotchas = _scan_gotchas(topic)
    sessions = _scan_session_history(topic)
    lessons = _scan_draft_lessons(topic)

    if args.as_json:
        print(_format_json(topic, gotchas, sessions, lessons))
    else:
        print(_format_text(topic, gotchas, sessions, lessons))


if __name__ == "__main__":
    main()
