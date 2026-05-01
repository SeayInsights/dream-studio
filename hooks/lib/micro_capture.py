"""Append-only one-line capture module for zero-friction daily learning.

Each call to ``append_capture`` writes a single timestamped line to
``~/.dream-studio/meta/today.md``.  ``rotate_daily`` archives the previous
day's file on the first capture of a new day so history is preserved.
``read_today`` returns all lines from the active capture file.
"""

from __future__ import annotations

import datetime
import shutil
from pathlib import Path

from . import paths


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _today_file() -> Path:
    return paths.meta_dir() / "today.md"


def _daily_dir() -> Path:
    d = paths.meta_dir() / "daily"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _extract_date_from_first_line(first_line: str) -> datetime.date | None:
    """Return the date embedded in a capture line (``HH:MM | …``), or None."""
    # Lines are prefixed with HH:MM.  The file-level date comes from the
    # header line written by rotate_daily: ``# YYYY-MM-DD``
    stripped = first_line.strip()
    if stripped.startswith("# "):
        try:
            return datetime.date.fromisoformat(stripped[2:].strip())
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rotate_daily() -> None:
    """Archive yesterday's capture file to ``meta/daily/YYYY-MM-DD.md``.

    Reads the first line of ``today.md`` for a date header.  If that date
    differs from today the file is moved to ``meta/daily/<date>.md``.  A new
    ``today.md`` with today's date header is created automatically by the
    next ``append_capture`` call.

    Safe to call repeatedly — does nothing when the file is already current.
    """
    today = datetime.date.today()
    today_file = _today_file()

    if not today_file.exists():
        return

    try:
        first_line = today_file.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return

    file_date = _extract_date_from_first_line(first_line)
    if file_date is None or file_date >= today:
        return

    dest = _daily_dir() / f"{file_date.isoformat()}.md"
    try:
        shutil.move(str(today_file), str(dest))
    except OSError:
        pass  # Don't crash if the move fails (e.g. cross-device)


def append_capture(skill: str, outcome: str, note: str) -> None:
    """Append one timestamped capture line to ``~/.dream-studio/meta/today.md``.

    Format::

        HH:MM | skill:<name> | outcome:<pass/fail/correction> | note:<one-line>

    Rotation is checked automatically before writing so the caller never needs
    to call ``rotate_daily`` manually.

    Args:
        skill:   The skill name (e.g. ``"core:build"``).
        outcome: One of ``pass``, ``fail``, or ``correction`` (freeform).
        note:    A single-line human-readable observation.
    """
    rotate_daily()

    today = datetime.date.today()
    now = datetime.datetime.now().strftime("%H:%M")
    line = f"{now} | skill:{skill} | outcome:{outcome} | note:{note}\n"

    today_file = _today_file()
    try:
        needs_header = not today_file.exists() or today_file.stat().st_size == 0
        with today_file.open("a", encoding="utf-8") as fh:
            if needs_header:
                fh.write(f"# {today.isoformat()}\n")
            fh.write(line)
    except OSError:
        pass  # Gracefully swallow filesystem-full or permission errors


def read_today() -> list[str]:
    """Return all lines from today's capture file.

    Returns an empty list when the file does not exist or cannot be read.
    The date-header line (``# YYYY-MM-DD``) is included in the output.
    """
    today_file = _today_file()
    try:
        return today_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
