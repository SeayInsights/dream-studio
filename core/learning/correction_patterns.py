"""Correction pattern detection and lesson drafting for on-agent-correction hook."""

from __future__ import annotations

import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path

from core.config import paths

# Add project root to path for canonical imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DEFAULT_TARGET_BASENAME = "director-corrections.md"
ACCUMULATION_THRESHOLD = 3
MAX_LOG_SIZE = 2 * 1024 * 1024  # 2 MB


def target_path() -> Path:
    """Get the corrections file path (from env or default)."""
    override = os.environ.get("DREAM_STUDIO_CORRECTIONS_PATH")
    if override:
        return Path(override)
    return paths.planning_dir() / DEFAULT_TARGET_BASENAME


def is_corrections_file(file_path: str) -> bool:
    """Check if the given path is the corrections file."""
    try:
        return Path(file_path).resolve() == target_path().resolve()
    except Exception:
        return file_path.replace("\\", "/").endswith("/" + DEFAULT_TARGET_BASENAME)


def extract_latest_correction(file_path: Path) -> dict | None:
    """Parse the latest correction block from corrections file."""
    if not file_path.exists():
        return None
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return None

    # Case-insensitive, flexible header matching
    match = re.search(r"^#{1,4}\s*corrections\b.*$", text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None

    block_start = match.end()
    next_section = re.search(
        r"^#{1,4}\s+(?!corrections\b)\w", text[block_start:], re.IGNORECASE | re.MULTILINE
    )
    block = (
        text[block_start : block_start + next_section.start()]
        if next_section
        else text[block_start:]
    )

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


def _log_lock(log_path: Path) -> tuple[Path, bool]:
    """Acquire a lock file for corrections.log."""
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
            archive = log_path.parent / f"corrections-{datetime.now(UTC).strftime('%Y%m%d')}.log"
            log_path.rename(archive)
    except OSError:
        pass


def _read_log_patterns(log_path: Path) -> list[str]:
    """Read all pattern entries from log."""
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


def log_correction(correction: dict, meta_dir: Path) -> None:
    """Append correction to log file."""
    pattern = correction.get("Pattern to apply", "").replace("\t", " ").strip()
    session = correction.get("Session", "unknown").replace("\t", " ").strip()
    timestamp = datetime.now(UTC).isoformat()

    log_path = meta_dir / "corrections.log"
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


def check_and_draft_lesson(correction: dict, meta_dir: Path) -> None:
    """Check for pattern accumulation and draft lesson in DB if threshold met."""
    from core.event_store.studio_db import insert_lesson

    pattern = correction.get("Pattern to apply", "").strip()
    if not pattern:
        return

    log_path = meta_dir / "corrections.log"
    patterns = _read_log_patterns(log_path)
    match_count = Counter(patterns).get(pattern, 0)

    if match_count < ACCUMULATION_THRESHOLD:
        return

    slug = re.sub(r"[^a-z0-9]+", "-", pattern.lower())[:50].strip("-") or "pattern"
    lesson_id = f"correction-pattern-{slug}"

    evidence_lines = []
    try:
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[2].strip() == pattern:
                evidence_lines.append(f"- {parts[0]} (session: {parts[1]})")
    except Exception:
        pass

    db_path = paths.state_dir() / "studio.db"
    inserted = insert_lesson(
        lesson_id,
        "on-agent-correction",
        f"Correction Pattern: {pattern}",
        what_happened=(
            f"Pattern '{pattern}' appeared {match_count}x in corrections. "
            f"Consider promoting to a permanent Derived Rule."
        ),
        evidence="\n".join(evidence_lines) if evidence_lines else None,
        confidence="medium",
        db_path=db_path,
    )
    if inserted:
        print(
            f"\n[dream-studio] SENSOR: Pattern repeated {match_count}x — draft lesson captured (DB lesson_id: {lesson_id})\n"
            f"  -> Pattern: {pattern}\n",
            flush=True,
        )


def print_logged_message(correction: dict) -> None:
    """Print confirmation message for logged correction."""
    pattern = correction.get("Pattern to apply", "").strip()
    session = correction.get("Session", "unknown").strip()
    print(
        f"\n[dream-studio] Director correction logged — session {session}\n"
        f"  -> Pattern: {pattern or '(none specified)'}\n",
        flush=True,
    )
