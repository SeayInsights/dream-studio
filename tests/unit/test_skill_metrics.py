"""Tests for hooks/lib/skill_metrics.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

import lib.skill_metrics as skill_metrics  # noqa: E402


class TestSkillMetricsMain:
    def _log(self, tmp_path: Path) -> Path:
        return tmp_path / ".dream-studio" / "state" / "skill-usage.jsonl"

    def test_writes_jsonl_record(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            with patch("sys.argv", ["skill_metrics.py", "dream-studio:build", "sonnet"]):
                skill_metrics.main()
        log = self._log(tmp_path)
        assert log.exists()
        record = json.loads(log.read_text())
        assert record["skill"] == "dream-studio:build"
        assert record["model"] == "sonnet"
        assert record["session"] == "dream-studio"
        assert "ts" in record

    def test_defaults_when_no_argv(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            with patch("sys.argv", ["skill_metrics.py"]):
                skill_metrics.main()
        record = json.loads(self._log(tmp_path).read_text())
        assert record["skill"] == "unknown"
        assert record["model"] == "unknown"

    def test_appends_multiple_records(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            with patch("sys.argv", ["skill_metrics.py", "build", "sonnet"]):
                skill_metrics.main()
            with patch("sys.argv", ["skill_metrics.py", "review", "opus"]):
                skill_metrics.main()
        lines = [l for l in self._log(tmp_path).read_text().splitlines() if l.strip()]
        assert len(lines) == 2
        assert json.loads(lines[1])["skill"] == "review"

    def test_only_skill_arg_model_defaults(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            with patch("sys.argv", ["skill_metrics.py", "ship"]):
                skill_metrics.main()
        record = json.loads(self._log(tmp_path).read_text())
        assert record["skill"] == "ship"
        assert record["model"] == "unknown"
