"""Tests for Item 6 PR B — skill telemetry buffer import and DB rollup."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.studio_db import get_skill_summaries, import_buffer, rebuild_summaries


def _buf(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _rows(skill: str, n: int, success: int = 1) -> list[dict]:
    return [
        {"skill_name": skill, "success": success, "invoked_at": f"2026-01-{i+1:02d}T00:00:00+00:00"}
        for i in range(n)
    ]


class TestImportBuffer:
    def test_imports_rows(self, tmp_path):
        buf = tmp_path / "buf.jsonl"
        _buf(buf, _rows("build", 1))
        assert import_buffer(buf, db_path=tmp_path / "t.db") == 1

    def test_idempotent_on_same_content(self, tmp_path):
        buf = tmp_path / "buf.jsonl"
        _buf(buf, _rows("build", 1))
        db = tmp_path / "t.db"
        assert import_buffer(buf, db_path=db) == 1
        assert import_buffer(buf, db_path=db) == 0

    def test_empty_buffer_returns_zero(self, tmp_path):
        buf = tmp_path / "buf.jsonl"
        buf.write_bytes(b"")
        assert import_buffer(buf, db_path=tmp_path / "t.db") == 0

    def test_missing_buffer_returns_zero(self, tmp_path):
        assert import_buffer(tmp_path / "no.jsonl", db_path=tmp_path / "t.db") == 0


class TestRebuildSummaries:
    def _load(self, tmp_path, skill: str, n: int, success: int = 1) -> None:
        buf = tmp_path / "buf.jsonl"
        _buf(buf, _rows(skill, n, success))
        import_buffer(buf, db_path=tmp_path / "t.db")

    def test_requires_five_runs(self, tmp_path):
        self._load(tmp_path, "think", 4)
        rebuild_summaries(db_path=tmp_path / "t.db")
        assert get_skill_summaries(db_path=tmp_path / "t.db") == []

    def test_summary_at_five_runs(self, tmp_path):
        self._load(tmp_path, "build", 5)
        rebuild_summaries(db_path=tmp_path / "t.db")
        rows = get_skill_summaries(db_path=tmp_path / "t.db")
        assert rows and rows[0]["skill_name"] == "build"

    def test_degraded_skill_shows_failure_ids(self, tmp_path):
        self._load(tmp_path, "mcp-build", 5, success=0)
        rebuild_summaries(db_path=tmp_path / "t.db")
        rows = get_skill_summaries(db_path=tmp_path / "t.db")
        assert rows[0]["recent_failure_ids"]

    def test_rebuild_is_idempotent(self, tmp_path):
        self._load(tmp_path, "plan", 5)
        rebuild_summaries(db_path=tmp_path / "t.db")
        rebuild_summaries(db_path=tmp_path / "t.db")
        assert len(get_skill_summaries(db_path=tmp_path / "t.db")) == 1

    def test_success_rate_computed_correctly(self, tmp_path):
        db = tmp_path / "t.db"
        buf1, buf2 = tmp_path / "b1.jsonl", tmp_path / "b2.jsonl"
        _buf(buf1, _rows("plan", 4, success=1))
        _buf(buf2, _rows("plan", 1, success=0))
        import_buffer(buf1, db_path=db)
        import_buffer(buf2, db_path=db)
        rebuild_summaries(db_path=db)
        rows = get_skill_summaries(db_path=db)
        assert abs(rows[0]["success_rate"] - 0.8) < 0.01
