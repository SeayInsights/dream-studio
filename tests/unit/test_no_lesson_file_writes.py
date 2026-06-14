"""Guard: no production source file writes lesson .md files to meta/draft-lessons/.

Lessons must be recorded via insert_lesson() into the raw_lessons DB table.
This test prevents reintroduction of file-based lesson writing.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories containing production Python source.
SOURCE_DIRS = [
    REPO_ROOT / "control",
    REPO_ROOT / "core",
    REPO_ROOT / "interfaces",
    REPO_ROOT / "spool",
    REPO_ROOT / "hooks",
]

# Regex patterns that indicate writing to a draft-lessons path.
_WRITE_PATTERNS = [
    re.compile(r"draft-lessons[^'\"\n]{0,80}write_text", re.IGNORECASE),
    re.compile(r"write_text[^'\"\n]{0,80}draft-lessons", re.IGNORECASE),
    re.compile(r"draft-lessons[^'\"\n]{0,80}open\s*\(.*[\"']w", re.IGNORECASE | re.DOTALL),
    re.compile(r"open\s*\([^)]*draft-lessons[^)]*[\"']w", re.IGNORECASE),
]


def _is_test_file(path: Path) -> bool:
    return "test_" in path.name or path.name.startswith("test")


def test_no_production_source_writes_to_draft_lessons_dir() -> None:
    violations: list[str] = []

    for src_dir in SOURCE_DIRS:
        if not src_dir.exists():
            continue
        for py_file in src_dir.rglob("*.py"):
            if _is_test_file(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for pat in _WRITE_PATTERNS:
                if pat.search(content):
                    rel = py_file.relative_to(REPO_ROOT)
                    violations.append(f"{rel}: matches '{pat.pattern}'")
                    break  # one violation per file is enough

    assert not violations, (
        "Production source files must not write lesson files to meta/draft-lessons/.\n"
        "Use insert_lesson() (core.event_store.studio_db) instead.\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )


def test_no_production_source_assigns_draft_lessons_path() -> None:
    """Guard: no source file assigns a non-None path under meta/draft-lessons/ to a variable."""
    violations: list[str] = []
    # Match: SOMETHING = Path("...draft-lessons...") or SOMETHING = "...draft-lessons..."
    assign_pattern = re.compile(
        r'=\s*(?:Path\s*\()?\s*["\'][^"\']*draft-lessons[^"\']*["\']',
        re.IGNORECASE,
    )

    for src_dir in SOURCE_DIRS:
        if not src_dir.exists():
            continue
        for py_file in src_dir.rglob("*.py"):
            if _is_test_file(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            if assign_pattern.search(content):
                rel = py_file.relative_to(REPO_ROOT)
                violations.append(str(rel))

    assert not violations, (
        "Production source files must not assign meta/draft-lessons paths.\n"
        "Lessons belong in raw_lessons DB — use insert_lesson().\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )
