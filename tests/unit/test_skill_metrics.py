"""Tests for hooks/lib/skill_metrics.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

import lib.skill_metrics as skill_metrics  # noqa: E402


def _run(tmp_path: Path, *argv: str) -> None:
    with patch.object(Path, "home", return_value=tmp_path), patch("sys.argv", list(argv)):
        skill_metrics.main()


def _log(tmp_path: Path) -> Path:
    return tmp_path / ".dream-studio" / "state" / "skill-usage.jsonl"


class TestSkillMetricsMain:
    def test_writes_jsonl_record(self, tmp_path: Path) -> None:
        _run(tmp_path, "skill_metrics.py", "dream-studio:build", "sonnet")
        record = json.loads(_log(tmp_path).read_text())
        assert record["skill"] == "dream-studio:build"
        assert record["model"] == "sonnet"
        assert record["session"] == "dream-studio"
        assert "ts" in record

    def test_defaults_when_no_argv(self, tmp_path: Path) -> None:
        _run(tmp_path, "skill_metrics.py")
        record = json.loads(_log(tmp_path).read_text())
        assert record["skill"] == "unknown"
        assert record["model"] == "unknown"

    def test_appends_multiple_records(self, tmp_path: Path) -> None:
        _run(tmp_path, "skill_metrics.py", "build", "sonnet")
        _run(tmp_path, "skill_metrics.py", "review", "opus")
        lines = [l for l in _log(tmp_path).read_text().splitlines() if l.strip()]
        assert len(lines) == 2
        assert json.loads(lines[1])["skill"] == "review"

    def test_only_skill_arg_model_defaults(self, tmp_path: Path) -> None:
        _run(tmp_path, "skill_metrics.py", "ship")
        record = json.loads(_log(tmp_path).read_text())
        assert record["skill"] == "ship"
        assert record["model"] == "unknown"


# ── __main__ guard (lines 35-38) ──────────────────────────────────────


_SKILL_METRICS_PATH = str(Path(__file__).resolve().parents[2] / "hooks" / "lib" / "skill_metrics.py")


def test_main_guard_happy_path(tmp_path: Path) -> None:
    import runpy
    with patch.object(Path, "home", return_value=tmp_path):
        runpy.run_path(_SKILL_METRICS_PATH, run_name="__main__")
    assert _log(tmp_path).exists()


def test_main_guard_exception_swallowed() -> None:
    import runpy
    with patch.object(Path, "mkdir", side_effect=OSError("disk full")):
        runpy.run_path(_SKILL_METRICS_PATH, run_name="__main__")  # must not raise
