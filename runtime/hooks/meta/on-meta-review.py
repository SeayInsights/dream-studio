#!/usr/bin/env python3
"""Hook: on-meta-review — weekly retrospective across recent sessions."""

import json
import os
import sys
from pathlib import Path


def _get_plugin_root() -> Path:
    sidecar = Path(__file__).resolve()
    for _ in range(8):
        candidate = sidecar / ".plugin-root"
        if candidate.is_file():
            try:
                return Path(candidate.read_text(encoding="utf-8").strip()).resolve()
            except Exception:
                pass
        sidecar = sidecar.parent
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[4]


_PLUGIN_ROOT = _get_plugin_root()
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))
if str(_PLUGIN_ROOT / "hooks") not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))

from core.config import paths
from core.learning.lesson_threshold import get_escalation_candidates
from control.review.engine import (
    draft_theme_lessons,
    generate_review,
    get_pending_drafts,
    parse_session_context,
    parse_token_log,
)
from core.utils.time import utcnow


def main() -> None:
    review_path = paths.meta_dir() / f"review-{utcnow().strftime('%Y-%m-%d')}.md"
    if review_path.exists():
        return
    sessions = parse_token_log() or parse_session_context()[0]
    if not sessions:
        return
    extra_themes = parse_session_context()[1] if not parse_token_log() else None
    review, themes = generate_review(sessions, extra_themes=extra_themes)
    drafted = draft_theme_lessons(themes, utcnow().isoformat())

    if drafted:
        print(
            f"\n[dream-studio] SENSOR: {len(drafted)} theme lesson(s) drafted:\n"
            + "".join(f"  -> {n}\n" for n in drafted),
            flush=True,
        )

    pending = get_pending_drafts()
    review += f"\n## Pending Draft Lessons ({len(pending)})\n\n" + (
        "".join(f"- `{n}`\n" for n in pending) + "Review and approve/reject each draft.\n"
        if pending
        else "None pending.\n"
    )
    review_path.write_text(review, encoding="utf-8")

    try:
        [
            print(
                f"\n[dream-studio] ⚠️  Skill '{c['skill']}' has {c['lesson_count']} draft lessons — consider update.\n",
                flush=True,
            )
            for c in get_escalation_candidates(threshold=3)
        ]
    except Exception:
        pass

    print(
        f"\n[dream-studio] Meta-review complete — {len(sessions)} sessions → {review_path}\n",
        flush=True,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "hook": "on-meta-review",
                "sessions_reviewed": len(sessions),
                "pending_drafts": len(pending),
                "output": str(review_path),
            }
        )
    )


if __name__ == "__main__":
    main()
