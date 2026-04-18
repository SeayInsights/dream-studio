#!/usr/bin/env python3
"""Hook: on-meta-review — weekly retrospective across recent sessions.

Trigger: Stop.
Reads `~/.dream-studio/meta/token-log.md`, aggregates the last seven
unique sessions, generates a themed retrospective, drafts lessons for
any theme occurring THEME_DRAFT_THRESHOLD+ times, and writes
`review-YYYY-MM-DD.md` into `~/.dream-studio/meta/`.
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths  # noqa: E402

THEME_DRAFT_THRESHOLD = 3
SESSION_COUNT = 7


def parse_token_log(count: int = SESSION_COUNT) -> list[dict]:
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
        # cols: ['', timestamp, session, model, prompt, completion, total, '']
        timestamp = cols[1]
        session_id = cols[2]
        model = cols[3]
        try:
            prompt_t = int(cols[4])
            completion_t = int(cols[5])
            total_t = int(cols[6])
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
        s["prompt_tokens"] = prompt_t
        s["completion_tokens"] = completion_t
        s["total_tokens"] = total_t
        s["turns"] += 1

    recent = list(sessions.values())[-count:]
    return recent


def format_duration(first: str, last: str) -> str:
    try:
        t1 = datetime.fromisoformat(first)
        t2 = datetime.fromisoformat(last)
        mins = int((t2 - t1).total_seconds() / 60)
        if mins < 1:
            return "<1m"
        if mins < 60:
            return f"{mins}m"
        return f"{mins // 60}h{mins % 60:02d}m"
    except Exception:
        return "?"


def generate_review(sessions: list[dict]) -> tuple[str, list[tuple[str, int]]]:
    if not sessions:
        return "# Weekly Review\n\nNo session data found in token-log.md.\n", []

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_tokens = sum(s.get("total_tokens", 0) for s in sessions)
    total_turns = sum(s.get("turns", 0) for s in sessions)

    lines = []
    for s in sessions:
        ts = s["first_seen"][:10]
        sid = s["session"][:8]
        model = s["model"]
        tokens = f"{s['total_tokens']:,}"
        turns = s["turns"]
        duration = format_duration(s["first_seen"], s["last_seen"])
        lines.append(f"| {ts} | {sid} | {model} | {tokens} | {turns} | {duration} |")
    sessions_table = "\n".join(lines)

    model_counts: dict[str, int] = {}
    for s in sessions:
        m = s.get("model", "unknown")
        model_counts[m] = model_counts.get(m, 0) + 1
    model_lines = "\n".join(f"- **{m}** ({c} session{'s' if c > 1 else ''})" for m, c in sorted(model_counts.items(), key=lambda x: -x[1]))

    avg_tokens = total_tokens // len(sessions) if sessions else 0
    max_session = max(sessions, key=lambda s: s["total_tokens"])
    max_sid = max_session["session"][:8]
    max_tokens = f"{max_session['total_tokens']:,}"

    themes: list[tuple[str, int]] = []
    for keyword, label in [
        ("opus", "opus"), ("sonnet", "sonnet"), ("haiku", "haiku"),
    ]:
        c = sum(1 for s in sessions if keyword in s.get("model", "").lower())
        if c > 0:
            themes.append((label, c))

    high_token_sessions = [s for s in sessions if s["total_tokens"] > 100_000]
    if high_token_sessions:
        themes.append(("high-context", len(high_token_sessions)))

    long_sessions = [s for s in sessions if s["turns"] > 10]
    if long_sessions:
        themes.append(("long-running", len(long_sessions)))

    themes.sort(key=lambda t: t[1], reverse=True)
    theme_lines = (
        "\n".join(f"- **{k}** ({c}x)" for k, c in themes[:6])
        if themes else "- No clear themes detected"
    )

    return (
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
        f"## Model Usage\n\n"
        f"{model_lines}\n\n"
        f"## Patterns\n\n"
        f"{theme_lines}\n\n"
        f"## Retrospective Prompts\n\n"
        f"1. Which sessions had the highest token burn? Was it productive or thrashing?\n"
        f"2. Are high-context sessions being compacted or handed off in time?\n"
        f"3. Is the model mix right? (Haiku for exploration, Sonnet for code, Opus for complex)\n"
        f"4. Any sessions that could have been shorter with better scoping?\n"
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


def main() -> None:
    sessions = parse_token_log(count=SESSION_COUNT)
    if not sessions:
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
