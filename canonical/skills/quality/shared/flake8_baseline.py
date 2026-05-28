"""Shared utility: flake8 baseline overlap detection for ds-quality:code-quality.

Used by audit/SKILL.md execution path to annotate findings that co-locate
with known-debt lines in the flake8 baseline, rather than suppressing them.

Policy: don't suppress co-located findings — they are still real signal.
Instead, annotate with "(also in flake8-baseline: known accepted debt)" so
operators can distinguish new findings from documented technical debt.
"""

from __future__ import annotations

import re
from pathlib import Path

_BASELINE_LINE_RE = re.compile(r"^(?P<path>[^:]+):(?P<line>\d+):\d+:\s+\w+\d+\s+")


def load_flake8_baseline(path: str | Path) -> set[tuple[str, int]]:
    """Parse a flake8 baseline file and return known-debt (file, line) pairs.

    Parses the standard flake8 output format:
        path/to/file.py:LINE:COL: CODE message

    Returns a set of (relative_file_path, line_number) tuples.
    Returns empty set if the baseline file is missing — don't crash.

    Args:
        path: Path to the flake8 baseline file.

    Returns:
        Set of (file_path, line_number) tuples for all baselined findings.
    """
    baseline_path = Path(path)
    if not baseline_path.is_file():
        return set()

    known_debt: set[tuple[str, int]] = set()
    try:
        for raw_line in baseline_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            m = _BASELINE_LINE_RE.match(line)
            if m:
                file_path = m.group("path").replace("\\", "/")
                line_num = int(m.group("line"))
                known_debt.add((file_path, line_num))
    except Exception:
        return set()

    return known_debt


def is_baselined(
    file_path: str,
    line_number: int,
    baseline: set[tuple[str, int]],
) -> bool:
    """Return True if (file_path, line_number) is in the flake8 baseline.

    Normalizes path separators before comparison.
    """
    normalized = file_path.replace("\\", "/")
    return (normalized, line_number) in baseline


BASELINE_ANNOTATION = "(also in flake8-baseline: known accepted debt)"
