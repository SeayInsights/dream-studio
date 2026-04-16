#!/usr/bin/env python3
"""Hook: on-meta-review — weekly retrospective across recent sessions.

Trigger: scheduled or on demand.
Reads `~/.dream-studio/planning/session-context.md`, extracts the last
seven session entries, generates a themed retrospective, drafts lessons
for any theme occurring THEME_DRAFT_THRESHOLD+ times, and writes
`review-YYYY-MM-DD.md` into `~/.dream-studio/meta/`.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths  # noqa: E402

THEME_DRAFT_THRESHOLD = 3
SESSION_CONTEXT_FILENAME = "session-context.md"


def session_context_path() -> Path:
    return paths.planning_dir() / SESSION_CONTEXT_FILENAME


def parse_sessions(text: str, count: int = 7) -> list[dict]:
    blocks = re.split(r"\n---\n", text)
    sessions = []
    for block in blocks:
        block = block.strip()
        if not block or "## Session End" not in block:
            continue
        entry = {}
        for pattern, key in [
            (r"\*\*Session:\*\*\s*(.+)", "session"),
            (r"\*\*Tokens used:\*\*\s*(\d+)", "tokens"),
            (r"\*\*Summary:\*\*\s*(.+)", "summary"),
            (r"## Session End — (.+)", "timestamp"),
        ]:
            m = re.search(pattern, block)
            if m:
                entry[key] = m.group(1).strip()
        if entry:
            sessions.append(entry)
    return sessions[-count:]


def generate_review(sessions: list[dict]) -> tuple[str, list[tuple[str, int]]]:
    if not sessions:
        return "# Weekly Review\n\nNo session data found for the review period.\n", []

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_tokens = sum(int(s.get("tokens", 0)) for s in sessions)

    lines = []
    for s in sessions:
        ts = s.get("timestamp", "unknown")[:10]
        name = s.get("session", "unknown")
        tokens = s.get("tokens", "0")
        summary = s.get("summary", "(no summary)")
        lines.append(f"| {ts} | {name} | {tokens} | {summary[:80]} |")
    sessions_table = "\n".join(lines)

    all_summaries = " ".join(s.get("summary", "") for s in sessions).lower()
    themes: list[tuple[str, int]] = []
    for keyword in [
        "build", "fix", "deploy", "refactor", "design", "debug",
        "migrate", "test", "hook", "skill", "agent", "review",
        "ship", "polish", "audit", "config",
    ]:
        c = all_summaries.count(keyword)
        if c > 0:
            themes.append((keyword, c))
    themes.sort(key=lambda t: t[1], reverse=True)
    theme_lines = (
        "\n".join(f"- **{k}** ({c}x)" for k, c in themes[:6])
        if themes else "- No clear themes detected"
    )

    return (
        f"# Weekly Meta-Review — {date}\n\n"
        f"**Period:** Last {len(sessions)} sessions\n"
        f"**Total tokens:** {total_tokens:,}\n\n"
        f"## Sessions\n\n"
        f"| Date | Session | Tokens | Summary |\n"
        f"|---|---|---|---|\n"
        f"{sessions_table}\n\n"
        f"## Themes\n\n"
        f"{theme_lines}\n\n"
        f"## Retrospective Prompts\n\n"
        f"1. What patterns repeated? Should any become permanent skills or rules?\n"
        f"2. Where did token usage spike? Was it justified or a sign of thrashing?\n"
        f"3. Which sessions advanced goals vs. maintained existing work?\n"
        f"4. Any corrections or escalations that suggest a systemic issue?\n"
        f"5. What should next week's focus be?\n"
    ), themes


def get_pending_drafts() -> list[str]:
    drafts_dir = paths.meta_dir() / "draft-lessons"
    if not drafts_dir.exists():
        return []
    return sorted(f.name for f in drafts_dir.glob("*.md"))


def draft_theme_lessons(themes: list[tuple[str, int]], timestamp: str) -> list[str]:
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
            f"---\n"
            f"type: draft-lesson\n"
            f"source: on-meta-review\n"
            f"status: draft\n"
            f"created: {timestamp}\n"
            f"---\n\n"
            f"## Recurring Theme: {keyword}\n\n"
            f"This theme appeared {count}x across the last 7 sessions.\n\n"
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


def main() -> None:
    context_path = session_context_path()
    if not context_path.exists():
        print("[on-meta-review] No session-context.md found — nothing to review.", flush=True)
        return

    text = context_path.read_text(encoding="utf-8")
    sessions = parse_sessions(text, count=7)
    if not sessions:
        print("[on-meta-review] No session entries found.", flush=True)
        return

    review, themes = generate_review(sessions)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    timestamp = datetime.now(timezone.utc).isoformat()

    drafted = draft_theme_lessons(themes, timestamp)
    if drafted:
        print(
            f"\n[dream-studio] SENSOR: {len(drafted)} theme lesson(s) drafted:\n"
            + "".join(f"  -> {name}\n" for name in drafted),
            flush=True,
        )

    pending = get_pending_drafts()
    if pending:
        review += (
            f"\n## Pending Draft Lessons ({len(pending)})\n\n"
            + "".join(f"- `{name}`\n" for name in pending)
            + "\nReview and approve/reject each draft.\n"
        )
    else:
        review += "\n## Pending Draft Lessons\n\nNone pending.\n"

    review_path = paths.meta_dir() / f"review-{date_str}.md"
    review_path.write_text(review, encoding="utf-8")

    print(
        f"\n[dream-studio] Weekly meta-review complete — {len(sessions)} sessions analyzed\n"
        f"  -> Written to: {review_path}\n"
        f"  -> Pending draft lessons: {len(pending)}\n",
        flush=True,
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "hook": "on-meta-review",
                "sessions_reviewed": len(sessions),
                "pending_drafts": len(pending),
                "themes_drafted": len(drafted),
                "output": str(review_path),
            }
        )
    )


if __name__ == "__main__":
    main()
