#!/usr/bin/env python3
"""Hook: on-agent-correction — log director corrections and accumulate patterns.

Trigger: PostToolUse on Edit|Write.
When the agent's corrections file is updated (by default
`~/.dream-studio/planning/director-corrections.md`; override via the
`DREAM_STUDIO_CORRECTIONS_PATH` env var), parse the newest correction
block, append a row to `~/.dream-studio/meta/corrections.log`, and —
once the same pattern appears 3+ times — draft a lesson for Director
review.
"""

from __future__ import annotations

import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib import paths  # noqa: E402

DEFAULT_TARGET_BASENAME = "director-corrections.md"
ACCUMULATION_THRESHOLD = 3
MAX_LOG_SIZE = 2 * 1024 * 1024  # 2 MB — archive and start fresh if exceeded


def target_path() -> Path:
    override = os.environ.get("DREAM_STUDIO_CORRECTIONS_PATH")
    if override:
        return Path(override)
    return paths.planning_dir() / DEFAULT_TARGET_BASENAME


def is_target_file(path: str) -> bool:
    try:
        return Path(path).resolve() == target_path().resolve()
    except Exception:
        return path.replace("\\", "/").endswith("/" + DEFAULT_TARGET_BASENAME)


def parse_latest_correction(text: str) -> dict | None:
    # Case-insensitive, flexible header matching (## Corrections, ### Corrections Found, etc.)
    match = re.search(r"^#{1,4}\s*corrections\b.*$", text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    block_start = match.end()
    # Stop at the next top-level section (## something other than corrections)
    next_section = re.search(r"^#{1,4}\s+(?!corrections\b)\w", text[block_start:], re.IGNORECASE | re.MULTILINE)
    block = text[block_start: block_start + next_section.start()] if next_section else text[block_start:]

    entries = re.split(r"\n(?=- Session:)", block)
    entries = [e.strip() for e in entries if e.strip().startswith("- Session:")]
    if not entries:
        return None
    latest = entries[-1]
    fields: dict[str, str] = {}
    for line in latest.split("\n"):
        line = line.strip().lstrip("- ")
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip()
    return fields or None


def _log_lock(log_path: Path) -> "tuple[Path, bool]":
    """Acquire a lock file for corrections.log. Returns (lock_path, acquired)."""
    lock_path = log_path.parent / f"{log_path.name}.lock"
    deadline = time.monotonic() + 2.0
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return lock_path, True
        except FileExistsError:
            if time.monotonic() > deadline:
                try:
                    lock_path.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            time.sleep(0.005)


def _archive_log_if_large(log_path: Path) -> None:
    """Archive corrections.log if it exceeds MAX_LOG_SIZE."""
    try:
        if log_path.exists() and log_path.stat().st_size > MAX_LOG_SIZE:
            archive = log_path.parent / f"corrections-{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"
            log_path.rename(archive)
    except OSError:
        pass


def append_to_log(session: str, pattern: str, timestamp: str) -> None:
    log_path = paths.meta_dir() / "corrections.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path, _ = _log_lock(log_path)
        try:
            _archive_log_if_large(log_path)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"{timestamp}\t{session}\t{pattern}\n")
        finally:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception as e:
        print(f"[on-agent-correction] failed to write log: {e}", file=sys.stderr)


def _read_log_patterns(log_path: Path) -> list[str]:
    """Read all pattern entries from log. Returns empty list on any error."""
    try:
        if not log_path.exists():
            return []
        text = log_path.read_text(encoding="utf-8")
        patterns = []
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[2].strip():
                patterns.append(parts[2].strip())
        return patterns
    except Exception:
        return []


def check_pattern_accumulation(pattern: str, timestamp: str) -> None:
    log_path = paths.meta_dir() / "corrections.log"
    patterns = _read_log_patterns(log_path)
    match_count = Counter(patterns).get(pattern, 0)
    if match_count < ACCUMULATION_THRESHOLD:
        return

    drafts_dir = paths.meta_dir() / "draft-lessons"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", pattern.lower())[:50].strip("-") or "pattern"
    draft_path = drafts_dir / f"correction-pattern-{slug}.md"
    if draft_path.exists():
        return

    evidence = []
    try:
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[2].strip() == pattern:
                evidence.append(f"- {parts[0]} (session: {parts[1]})")
    except Exception:
        pass

    draft = (
        f"---\n"
        f"type: draft-lesson\n"
        f"source: on-agent-correction\n"
        f"status: draft\n"
        f"created: {timestamp}\n"
        f"---\n\n"
        f"## Proposed Lesson\n\n"
        f"**Pattern:** {pattern}\n\n"
        f"This pattern has appeared in {match_count} corrections. Consider promoting "
        f"it to a permanent Derived Rule in director-corrections.md.\n\n"
        f"## Evidence ({match_count} occurrences)\n\n"
        + "\n".join(evidence) + "\n\n"
        + "## Director Action\n\n"
        + "- [ ] Promote to Derived Rule\n"
        + "- [ ] Edit and promote\n"
        + "- [ ] Reject (delete this file)\n"
    )
    draft_path.write_text(draft, encoding="utf-8")
    print(
        f"\n[dream-studio] SENSOR: Pattern repeated {match_count}x — draft lesson created\n"
        f"  -> Pattern: {pattern}\n"
        f"  -> Review: {draft_path}\n",
        flush=True,
    )


def main() -> None:
    file_path = os.environ.get("CLAUDE_FILE_PATH", "").strip()
    if not file_path or not is_target_file(file_path):
        return
    p = Path(file_path)
    if not p.exists():
        return
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return

    correction = parse_latest_correction(text)
    if not correction:
        return

    pattern = correction.get("Pattern to apply", "").replace("\t", " ").strip()
    session = correction.get("Session", "unknown").replace("\t", " ").strip()
    timestamp = datetime.now(timezone.utc).isoformat()

    print(
        f"\n[dream-studio] Director correction logged — session {session}\n"
        f"  -> Pattern: {pattern or '(none specified)'}\n",
        flush=True,
    )

    append_to_log(session, pattern, timestamp)
    if pattern:
        try:
            check_pattern_accumulation(pattern, timestamp)
        except Exception:
            pass


if __name__ == "__main__":
    main()
