"""Review engine for meta-review hook - session retrospective analysis."""

from __future__ import annotations

import sys
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from core.config import paths
from core.learning.lesson_threshold import get_escalation_candidates
from core.utils.time import utcnow

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
THEME_DRAFT_THRESHOLD = 3
SESSION_COUNT = 7

_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "some",
    "did",
    "work",
    "that",
    "this",
    "was",
    "is",
    "it",
    "be",
    "by",
    "from",
    "as",
    "not",
    "are",
    "has",
    "have",
    "do",
    "done",
    "been",
}


def parse_token_log(count: int = SESSION_COUNT) -> list[dict]:
    """Parse token-log.md and return recent sessions."""
    log_path = paths.meta_dir() / "token-log.md"
    if not log_path.exists():
        return []

    sessions: OrderedDict[str, dict] = OrderedDict()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("| Timestamp") or line.startswith("|---"):
            continue
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 7:
            continue
        timestamp, session_id, model = cols[1], cols[2], cols[3]
        try:
            prompt_t, completion_t, total_t = int(cols[4]), int(cols[5]), int(cols[6])
        except (ValueError, IndexError):
            continue

        if session_id not in sessions:
            sessions[session_id] = {
                "session": session_id,
                "model": model,
                "first_seen": timestamp,
                "last_seen": timestamp,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "turns": 0,
            }
        s = sessions[session_id]
        s["last_seen"] = timestamp
        s["prompt_tokens"], s["completion_tokens"], s["total_tokens"] = (
            prompt_t,
            completion_t,
            total_t,
        )
        s["turns"] += 1

    return list(sessions.values())[-count:]


def parse_session_context(count: int = SESSION_COUNT) -> tuple[list[dict], list[tuple[str, int]]]:
    """Read session-context.md fallback."""
    ctx_path = paths.planning_dir() / "session-context.md"
    if not ctx_path.exists():
        return [], []

    sessions, summaries = [], []
    for line in ctx_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("- **") and "**:" in line:
            sid = line.split("**")[1]
            summary = line.split(":", 1)[1].strip()
            sessions.append(
                {
                    "session": sid,
                    "model": "unknown",
                    "first_seen": "",
                    "last_seen": "",
                    "total_tokens": 0,
                    "turns": 0,
                }
            )
            summaries.append(summary)

    themes = _extract_summary_themes(summaries) if summaries else []
    return sessions[-count:], themes


def _extract_summary_themes(summaries: list[str]) -> list[tuple[str, int]]:
    """Count keyword frequency across summaries."""
    counts: dict[str, int] = {}
    for summary in summaries:
        words = set(re.findall(r"\b[a-z][a-z0-9-]*\b", summary.lower()))
        for w in words:
            if w not in _STOPWORDS and len(w) > 2:
                counts[w] = counts.get(w, 0) + 1
    return [(w, c) for w, c in counts.items() if c >= 2]


def format_duration(start: str, end: str) -> str:
    """Format duration between timestamps."""
    try:
        t1 = datetime.fromisoformat(start.replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(end.replace("Z", "+00:00"))
        mins = int((t2 - t1).total_seconds() / 60)
        return f"{mins}m" if mins < 60 else f"{mins // 60}h{mins % 60:02d}m"
    except Exception:
        return "?"


def generate_review(
    sessions: list[dict], extra_themes: list[tuple[str, int]] | None = None
) -> tuple[str, list[tuple[str, int]]]:
    """Generate review markdown from sessions."""
    if not sessions:
        return "# Weekly Review\n\nNo session data found.\n", []

    date = utcnow().strftime("%Y-%m-%d")
    total_tokens = sum(s.get("total_tokens", 0) for s in sessions)
    total_turns = sum(s.get("turns", 0) for s in sessions)
    avg_tokens = total_tokens // len(sessions) if sessions else 0
    max_session = max(sessions, key=lambda s: s["total_tokens"])
    max_sid, max_tokens = max_session["session"][:8], f"{max_session['total_tokens']:,}"

    sessions_table = "\n".join(
        f"| {s['first_seen'][:10]} | {s['session'][:8]} | {s['model']} | {s['total_tokens']:,} | {s['turns']} | {format_duration(s['first_seen'], s['last_seen'])} |"
        for s in sessions
    )

    model_counts: dict[str, int] = {}
    for s in sessions:
        model_counts[s.get("model", "unknown")] = model_counts.get(s.get("model", "unknown"), 0) + 1
    model_lines = "\n".join(
        f"- **{m}** ({c} session{'s' if c > 1 else ''})"
        for m, c in sorted(model_counts.items(), key=lambda x: -x[1])
    )

    themes: list[tuple[str, int]] = []
    for keyword, label in [("opus", "opus"), ("sonnet", "sonnet"), ("haiku", "haiku")]:
        c = sum(1 for s in sessions if keyword in s.get("model", "").lower())
        if c > 0:
            themes.append((label, c))

    if high_token_sessions := [s for s in sessions if s["total_tokens"] > 100_000]:
        themes.append(("high-context", len(high_token_sessions)))
    if long_sessions := [s for s in sessions if s["turns"] > 10]:
        themes.append(("long-running", len(long_sessions)))

    if extra_themes:
        theme_dict = dict(themes)
        for k, v in extra_themes:
            theme_dict[k] = theme_dict.get(k, 0) + v
        themes = list(theme_dict.items())

    themes.sort(key=lambda t: t[1], reverse=True)
    theme_lines = (
        "\n".join(f"- **{k}** ({c}x)" for k, c in themes[:6])
        if themes
        else "- No clear themes detected"
    )

    review = (
        f"# Weekly Meta-Review — {date}\n\n"
        f"**Period:** Last {len(sessions)} sessions\n"
        f"**Total tokens:** {total_tokens:,}\n"
        f"**Total turns:** {total_turns}\n"
        f"**Avg tokens/session:** {avg_tokens:,}\n"
        f"**Heaviest session:** {max_sid} ({max_tokens} tokens)\n\n"
        f"## Sessions\n\n"
        f"| Date | Session | Model | Tokens | Turns | Duration |\n"
        f"|---|---|---|---|---|---|\n"
        f"{sessions_table}\n\n"
        f"## Model Usage\n\n{model_lines}\n\n"
        f"## Patterns\n\n{theme_lines}\n\n"
        f"## Retrospective Prompts\n\n"
        f"1. Which sessions had the highest token burn? Was it productive or thrashing?\n"
        f"2. Are high-context sessions being compacted or handed off in time?\n"
        f"3. Is the model mix right? (Haiku for exploration, Sonnet for code, Opus for complex)\n"
        f"4. Any sessions that could have been shorter with better scoping?\n"
        f"5. What should next week's focus be?\n"
    )
    return review, themes


def get_pending_drafts() -> list[str]:
    """Get list of pending draft lessons."""
    drafts_dir = paths.meta_dir() / "draft-lessons"
    return sorted(f.name for f in drafts_dir.glob("*.md")) if drafts_dir.exists() else []


def draft_theme_lessons(themes: list[tuple[str, int]], timestamp: str) -> list[str]:
    """Draft lessons for recurring themes."""
    drafts_dir = paths.meta_dir() / "draft-lessons"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    drafted = []
    for keyword, count in themes:
        if count < THEME_DRAFT_THRESHOLD:
            continue
        slug = keyword.lower().strip()
        draft_path = drafts_dir / f"theme-{slug}-{timestamp[:10]}.md"
        if draft_path.exists():
            continue
        draft = (
            f"---\ntype: draft-lesson\nsource: on-meta-review\nstatus: draft\ncreated: {timestamp}\n---\n\n"
            f"## Recurring Theme: {keyword}\n\n"
            f"This theme appeared {count}x across the last {SESSION_COUNT} sessions.\n\n"
            f"A recurring theme may indicate:\n"
            f"- A sustained initiative (good — track progress)\n"
            f"- A recurring problem (needs a permanent fix or new skill)\n"
            f"- A workflow gap (the system keeps needing manual intervention)\n\n"
            f"## Director Action\n\n"
            f"- [ ] Sustained initiative — no action needed\n"
            f"- [ ] Recurring problem — create a skill or rule to address it\n"
            f"- [ ] Reject (delete this file)\n"
        )
        draft_path.write_text(draft, encoding="utf-8")
        drafted.append(draft_path.name)
    return drafted
