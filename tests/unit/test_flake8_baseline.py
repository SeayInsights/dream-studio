"""Tests for canonical/skills/quality/shared/flake8_baseline.py

Verifies:
- load_flake8_baseline() parses the standard flake8 output format
- is_baselined() correctly identifies co-located findings
- Missing baseline file returns empty set (no crash)
- Path normalization handles Windows vs POSIX separators
- Comments and blank lines are skipped
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canonical.skills.quality.shared.flake8_baseline import (
    BASELINE_ANNOTATION,
    is_baselined,
    load_flake8_baseline,
)


@pytest.fixture
def baseline_file(tmp_path: Path) -> Path:
    content = """\
# Dream Studio flake8 baseline.
# Existing findings are tracked debt.

core/event_store/studio_db.py:341:9: E501 line too long (91 > 88 characters)
interfaces/cli/ds.py:1714:1: E302 expected 2 blank lines, found 1
projections/api/routes/insights.py:7:1: F401 'datetime' imported but unused

"""
    f = tmp_path / "flake8-baseline.txt"
    f.write_text(content, encoding="utf-8")
    return f


def test_load_baseline_parses_file_and_line(baseline_file: Path) -> None:
    baseline = load_flake8_baseline(baseline_file)
    assert ("core/event_store/studio_db.py", 341) in baseline
    assert ("interfaces/cli/ds.py", 1714) in baseline
    assert ("projections/api/routes/insights.py", 7) in baseline


def test_load_baseline_skips_comments_and_blank_lines(baseline_file: Path) -> None:
    baseline = load_flake8_baseline(baseline_file)
    # Only 3 real findings
    assert len(baseline) == 3


def test_load_baseline_missing_file_returns_empty_set(tmp_path: Path) -> None:
    result = load_flake8_baseline(tmp_path / "nonexistent.txt")
    assert result == set()
    assert isinstance(result, set)


def test_load_baseline_empty_file_returns_empty_set(tmp_path: Path) -> None:
    f = tmp_path / "empty.txt"
    f.write_text("# only comments\n\n", encoding="utf-8")
    assert load_flake8_baseline(f) == set()


def test_is_baselined_true_when_in_baseline(baseline_file: Path) -> None:
    baseline = load_flake8_baseline(baseline_file)
    assert is_baselined("core/event_store/studio_db.py", 341, baseline)


def test_is_baselined_false_when_not_in_baseline(baseline_file: Path) -> None:
    baseline = load_flake8_baseline(baseline_file)
    assert not is_baselined("core/event_store/studio_db.py", 999, baseline)
    assert not is_baselined("some_other_file.py", 341, baseline)


def test_is_baselined_normalizes_windows_path_separators(baseline_file: Path) -> None:
    baseline = load_flake8_baseline(baseline_file)
    # Simulate a finding reported with Windows-style path
    assert is_baselined("core\\event_store\\studio_db.py", 341, baseline)


def test_load_baseline_normalizes_backslash_in_baseline(tmp_path: Path) -> None:
    # Baseline written with Windows-style paths (can happen on Windows CI)
    content = "core\\event_store\\studio_db.py:100:1: E501 line too long\n"
    f = tmp_path / "win-baseline.txt"
    f.write_text(content, encoding="utf-8")
    baseline = load_flake8_baseline(f)
    assert ("core/event_store/studio_db.py", 100) in baseline


def test_baseline_annotation_string_is_defined() -> None:
    assert isinstance(BASELINE_ANNOTATION, str)
    assert "flake8-baseline" in BASELINE_ANNOTATION
    assert "debt" in BASELINE_ANNOTATION


def test_load_real_baseline_does_not_crash() -> None:
    """Smoke test against the live baseline file if present."""
    real_path = Path("runtime/config/release-gates/flake8-baseline.txt")
    result = load_flake8_baseline(real_path)
    # Either found entries or empty set — no exception
    assert isinstance(result, set)
    if result:
        file_path, line_num = next(iter(result))
        assert isinstance(file_path, str)
        assert isinstance(line_num, int)
        assert line_num > 0
