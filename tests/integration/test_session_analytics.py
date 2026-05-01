"""Integration tests for session parsing and analytics (session_parser module)."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

# Make the hooks/lib package importable without an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))
from lib.session_parser import extract_blockers, parse_handoff, parse_recap, scan_sessions

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

HANDOFF_SAMPLE: dict = {
    "topic": "test-feature",
    "date": "2026-05-01",
    "project_root": "/tmp/test",
    "plan_path": ".planning/specs/test/plan.md",
    "pipeline_phase": "build",
    "current_task_id": "3.2",
    "current_task_name": "Wire up API",
    "tasks_completed": 5,
    "tasks_total": 12,
    "branch": "feat/test",
    "last_commit": "abc1234",
    "working": ["auth flow"],
    "broken": [{"item": "test suite", "detail": "2 failures"}],
    "pending_decisions": [],
    "active_files": ["src/api.ts"],
    "next_action": "Fix test failures",
}

RECAP_SAMPLE: str = """\
# Recap: test-feature
Date: 2026-05-01

## What was built
- src/api.ts: new endpoint

## Decisions
- Used REST over GraphQL: simpler for MVP

## Risk flags
- test coverage low: deferred

## Remaining work
- Add error handling

## Next step
Add validation middleware
"""


def _make_session_dir(root: Path, date_str: str) -> Path:
    """Create a dated session directory under root and return it."""
    d = root / date_str
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_handoff(session_dir: Path, data: dict, name: str = "handoff-01.json") -> Path:
    p = session_dir / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _write_recap(session_dir: Path, content: str, name: str = "recap-01.md") -> Path:
    p = session_dir / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Test 1 — parse_handoff with full sample data
# ---------------------------------------------------------------------------

class TestParseHandoffJson:
    def test_all_top_level_keys_present(self, tmp_path: Path) -> None:
        """parse_handoff returns a dict containing every standardised key."""
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_handoff(d, HANDOFF_SAMPLE)

        result = parse_handoff(path)

        expected_keys = {
            "type", "date", "topic", "phase", "tasks_completed",
            "tasks_total", "broken_items", "corrections", "skills_used",
            "branch", "next_action", "raw",
        }
        assert expected_keys.issubset(result.keys()), (
            f"Missing keys: {expected_keys - result.keys()}"
        )

    def test_scalar_fields_correctly_extracted(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_handoff(d, HANDOFF_SAMPLE)

        result = parse_handoff(path)

        assert result["type"] == "handoff"
        assert result["date"] == "2026-05-01"
        assert result["topic"] == "test-feature"
        assert result["phase"] == "build"
        assert result["tasks_completed"] == 5
        assert result["tasks_total"] == 12
        assert result["branch"] == "feat/test"
        assert result["next_action"] == "Fix test failures"

    def test_broken_items_extracted_from_dict_format(self, tmp_path: Path) -> None:
        """Broken items given as dicts with 'item' key are unpacked to strings."""
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_handoff(d, HANDOFF_SAMPLE)

        result = parse_handoff(path)

        assert isinstance(result["broken_items"], list)
        assert "test suite" in result["broken_items"]

    def test_skills_inferred_from_phase(self, tmp_path: Path) -> None:
        """skills_used is inferred from pipeline_phase and should be non-empty."""
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_handoff(d, HANDOFF_SAMPLE)

        result = parse_handoff(path)

        assert isinstance(result["skills_used"], list)
        assert len(result["skills_used"]) > 0
        assert "dream-studio:core" in result["skills_used"]

    def test_raw_field_contains_original_data(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_handoff(d, HANDOFF_SAMPLE)

        result = parse_handoff(path)

        assert result["raw"] == HANDOFF_SAMPLE

    def test_no_parse_error_on_valid_file(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_handoff(d, HANDOFF_SAMPLE)

        result = parse_handoff(path)

        assert "_parse_error" not in result


# ---------------------------------------------------------------------------
# Test 2 — parse_handoff with minimal / missing optional fields
# ---------------------------------------------------------------------------

class TestParseHandoffMissingFields:
    """parse_handoff handles minimal JSON gracefully with correct defaults."""

    MINIMAL: dict = {"topic": "minimal-topic"}

    def test_returns_dict_without_error(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-04-15")
        path = _write_handoff(d, self.MINIMAL)

        result = parse_handoff(path)

        assert "_parse_error" not in result

    def test_numeric_defaults_are_zero(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-04-15")
        path = _write_handoff(d, self.MINIMAL)

        result = parse_handoff(path)

        assert result["tasks_completed"] == 0
        assert result["tasks_total"] == 0

    def test_list_defaults_are_empty(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-04-15")
        path = _write_handoff(d, self.MINIMAL)

        result = parse_handoff(path)

        assert result["broken_items"] == []
        assert result["corrections"] == []

    def test_string_defaults_are_empty(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-04-15")
        path = _write_handoff(d, self.MINIMAL)

        result = parse_handoff(path)

        assert result["phase"] == ""
        assert result["branch"] == ""
        assert result["next_action"] == ""

    def test_date_falls_back_to_directory_name(self, tmp_path: Path) -> None:
        """When 'date' is absent from JSON, directory name is used."""
        d = _make_session_dir(tmp_path, "2026-04-15")
        path = _write_handoff(d, self.MINIMAL)

        result = parse_handoff(path)

        assert result["date"] == "2026-04-15"

    def test_skills_used_defaults_to_core(self, tmp_path: Path) -> None:
        """Without a recognisable phase or topic, skills_used defaults to core."""
        d = _make_session_dir(tmp_path, "2026-04-15")
        path = _write_handoff(d, self.MINIMAL)

        result = parse_handoff(path)

        # topic is "minimal-topic" which contains no known keyword; phase is ""
        assert "dream-studio:core" in result["skills_used"]

    def test_missing_file_returns_error_key(self, tmp_path: Path) -> None:
        path = tmp_path / "2026-04-15" / "handoff-ghost.json"

        result = parse_handoff(path)

        assert "_parse_error" in result

    def test_invalid_json_returns_error_key(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-04-15")
        p = d / "handoff-bad.json"
        p.write_text("{not valid json", encoding="utf-8")

        result = parse_handoff(p)

        assert "_parse_error" in result


# ---------------------------------------------------------------------------
# Test 3 — parse_recap with full sample markdown
# ---------------------------------------------------------------------------

class TestParseRecapMd:
    def test_all_top_level_keys_present(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_recap(d, RECAP_SAMPLE)

        result = parse_recap(path)

        expected_keys = {
            "type", "date", "topic", "what_built", "decisions",
            "risk_flags", "remaining", "next_step", "corrections",
        }
        assert expected_keys.issubset(result.keys())

    def test_type_is_recap(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_recap(d, RECAP_SAMPLE)

        result = parse_recap(path)

        assert result["type"] == "recap"

    def test_date_extracted_from_date_line(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_recap(d, RECAP_SAMPLE)

        result = parse_recap(path)

        assert result["date"] == "2026-05-01"

    def test_topic_extracted_from_heading(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_recap(d, RECAP_SAMPLE)

        result = parse_recap(path)

        assert result["topic"] == "test-feature"

    def test_what_built_extracted(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_recap(d, RECAP_SAMPLE)

        result = parse_recap(path)

        assert isinstance(result["what_built"], list)
        assert any("api.ts" in item for item in result["what_built"])

    def test_decisions_extracted(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_recap(d, RECAP_SAMPLE)

        result = parse_recap(path)

        assert isinstance(result["decisions"], list)
        assert any("REST" in item for item in result["decisions"])

    def test_risk_flags_extracted(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_recap(d, RECAP_SAMPLE)

        result = parse_recap(path)

        assert isinstance(result["risk_flags"], list)
        assert any("test coverage" in item for item in result["risk_flags"])

    def test_remaining_extracted(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_recap(d, RECAP_SAMPLE)

        result = parse_recap(path)

        assert isinstance(result["remaining"], list)
        assert any("error handling" in item for item in result["remaining"])

    def test_next_step_extracted(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_recap(d, RECAP_SAMPLE)

        result = parse_recap(path)

        assert "validation middleware" in result["next_step"]

    def test_no_parse_error_on_valid_file(self, tmp_path: Path) -> None:
        d = _make_session_dir(tmp_path, "2026-05-01")
        path = _write_recap(d, RECAP_SAMPLE)

        result = parse_recap(path)

        assert "_parse_error" not in result


# ---------------------------------------------------------------------------
# Test 4 — scan_sessions filters by date window
# ---------------------------------------------------------------------------

class TestScanSessionsFiltersByDate:
    def _today_offset(self, offset_days: int) -> str:
        return (date.today() - timedelta(days=offset_days)).isoformat()

    def test_returns_recent_sessions(self, tmp_path: Path) -> None:
        """Sessions within the day window are returned."""
        recent_date = self._today_offset(3)
        d = _make_session_dir(tmp_path, recent_date)
        _write_handoff(d, {**HANDOFF_SAMPLE, "date": recent_date})

        results = scan_sessions(tmp_path, days=7)

        assert len(results) == 1
        assert results[0]["date"] == recent_date

    def test_excludes_sessions_older_than_window(self, tmp_path: Path) -> None:
        """Sessions beyond days= threshold are excluded."""
        old_date = self._today_offset(30)
        d = _make_session_dir(tmp_path, old_date)
        _write_handoff(d, {**HANDOFF_SAMPLE, "date": old_date})

        results = scan_sessions(tmp_path, days=7)

        assert len(results) == 0

    def test_only_recent_returned_when_mixed(self, tmp_path: Path) -> None:
        """Only sessions within the window appear when old and new sessions coexist."""
        recent_date = self._today_offset(2)
        old_date = self._today_offset(14)

        d_recent = _make_session_dir(tmp_path, recent_date)
        _write_handoff(d_recent, {**HANDOFF_SAMPLE, "date": recent_date}, "handoff-recent.json")

        d_old = _make_session_dir(tmp_path, old_date)
        _write_handoff(d_old, {**HANDOFF_SAMPLE, "date": old_date}, "handoff-old.json")

        results = scan_sessions(tmp_path, days=7)

        dates = [r["date"] for r in results]
        assert recent_date in dates
        assert old_date not in dates

    def test_results_sorted_descending_by_date(self, tmp_path: Path) -> None:
        """scan_sessions returns sessions sorted most-recent-first."""
        date_a = self._today_offset(1)
        date_b = self._today_offset(3)
        date_c = self._today_offset(5)

        for d_str in (date_a, date_b, date_c):
            d = _make_session_dir(tmp_path, d_str)
            _write_handoff(d, {**HANDOFF_SAMPLE, "date": d_str})

        results = scan_sessions(tmp_path, days=7)

        returned_dates = [r["date"] for r in results]
        assert returned_dates == sorted(returned_dates, reverse=True)

    def test_empty_root_returns_empty_list(self, tmp_path: Path) -> None:
        results = scan_sessions(tmp_path, days=7)
        assert results == []

    def test_non_existent_root_returns_empty_list(self, tmp_path: Path) -> None:
        ghost = tmp_path / "no-such-dir"
        results = scan_sessions(ghost, days=7)
        assert results == []

    def test_skips_non_date_directories(self, tmp_path: Path) -> None:
        """Directories with non-date names are silently ignored."""
        junk_dir = tmp_path / "misc-stuff"
        junk_dir.mkdir()
        _write_handoff(junk_dir, HANDOFF_SAMPLE)

        results = scan_sessions(tmp_path, days=7)

        assert results == []

    def test_includes_both_handoff_and_recap_files(self, tmp_path: Path) -> None:
        """scan_sessions picks up both handoff JSON and recap MD in the same dir."""
        recent_date = self._today_offset(1)
        d = _make_session_dir(tmp_path, recent_date)
        _write_handoff(d, {**HANDOFF_SAMPLE, "date": recent_date})
        _write_recap(d, RECAP_SAMPLE.replace("2026-05-01", recent_date))

        results = scan_sessions(tmp_path, days=7)

        types = {r["type"] for r in results}
        assert "handoff" in types
        assert "recap" in types


# ---------------------------------------------------------------------------
# Test 5 — extract_blockers frequency counting
# ---------------------------------------------------------------------------

class TestExtractBlockersCountsFrequency:
    def _make_handoff_session(
        self, topic: str, broken: list[str], src_date: str = "2026-05-01"
    ) -> dict:
        return {
            "type": "handoff",
            "date": src_date,
            "topic": topic,
            "broken_items": broken,
        }

    def _make_recap_session(
        self, topic: str, risk_flags: list[str], src_date: str = "2026-05-01"
    ) -> dict:
        return {
            "type": "recap",
            "date": src_date,
            "topic": topic,
            "risk_flags": risk_flags,
        }

    def test_returns_list_of_dicts(self) -> None:
        sessions = [self._make_handoff_session("feat-a", ["db timeout"])]
        result = extract_blockers(sessions)
        assert isinstance(result, list)
        assert all(isinstance(r, dict) for r in result)

    def test_each_entry_has_required_keys(self) -> None:
        sessions = [self._make_handoff_session("feat-a", ["db timeout"])]
        result = extract_blockers(sessions)
        for entry in result:
            assert {"item", "source_date", "source_topic", "frequency"}.issubset(entry.keys())

    def test_single_occurrence_has_frequency_one(self) -> None:
        sessions = [self._make_handoff_session("feat-a", ["flaky test"])]
        result = extract_blockers(sessions)
        assert len(result) == 1
        assert result[0]["item"] == "flaky test"
        assert result[0]["frequency"] == 1

    def test_overlapping_items_counted_across_sessions(self) -> None:
        """The same blocker in three sessions should have frequency == 3."""
        sessions = [
            self._make_handoff_session("feat-a", ["test suite broken"], "2026-04-29"),
            self._make_handoff_session("feat-b", ["test suite broken"], "2026-04-30"),
            self._make_handoff_session("feat-c", ["test suite broken"], "2026-05-01"),
        ]
        result = extract_blockers(sessions)
        entry = next((r for r in result if r["item"] == "test suite broken"), None)
        assert entry is not None
        assert entry["frequency"] == 3

    def test_duplicate_within_same_session_counted_once(self) -> None:
        """A blocker listed twice in one session still only counts as frequency 1."""
        sessions = [
            self._make_handoff_session("feat-a", ["flaky test", "flaky test"])
        ]
        result = extract_blockers(sessions)
        entry = next((r for r in result if r["item"] == "flaky test"), None)
        assert entry is not None
        assert entry["frequency"] == 1

    def test_sorted_by_frequency_descending(self) -> None:
        sessions = [
            self._make_handoff_session("feat-a", ["rare bug"], "2026-04-29"),
            self._make_handoff_session("feat-b", ["common issue", "rare bug"], "2026-04-30"),
            self._make_handoff_session("feat-c", ["common issue"], "2026-05-01"),
        ]
        result = extract_blockers(sessions)
        frequencies = [r["frequency"] for r in result]
        assert frequencies == sorted(frequencies, reverse=True)

    def test_most_frequent_blocker_is_first(self) -> None:
        sessions = [
            self._make_handoff_session("feat-a", ["high-freq"], "2026-04-28"),
            self._make_handoff_session("feat-b", ["high-freq", "low-freq"], "2026-04-29"),
            self._make_handoff_session("feat-c", ["high-freq"], "2026-04-30"),
        ]
        result = extract_blockers(sessions)
        assert result[0]["item"] == "high-freq"
        assert result[0]["frequency"] == 3

    def test_source_date_reflects_most_recent_occurrence(self) -> None:
        """source_date on the result should be the latest date this item appeared."""
        sessions = [
            self._make_handoff_session("feat-a", ["recurring bug"], "2026-04-20"),
            self._make_handoff_session("feat-b", ["recurring bug"], "2026-05-01"),
        ]
        result = extract_blockers(sessions)
        entry = next(r for r in result if r["item"] == "recurring bug")
        assert entry["source_date"] == "2026-05-01"

    def test_recap_risk_flags_counted_as_blockers(self) -> None:
        """extract_blockers treats recap risk_flags as blockers, not broken_items."""
        sessions = [
            self._make_recap_session("feat-a", ["low test coverage"], "2026-05-01")
        ]
        result = extract_blockers(sessions)
        entry = next((r for r in result if r["item"] == "low test coverage"), None)
        assert entry is not None
        assert entry["frequency"] == 1

    def test_mixed_handoff_and_recap_sessions(self) -> None:
        """Blockers are aggregated across both session types."""
        sessions = [
            self._make_handoff_session("feat-a", ["shared issue"], "2026-04-30"),
            self._make_recap_session("feat-b", ["shared issue"], "2026-05-01"),
        ]
        result = extract_blockers(sessions)
        entry = next((r for r in result if r["item"] == "shared issue"), None)
        assert entry is not None
        assert entry["frequency"] == 2

    def test_empty_sessions_returns_empty_list(self) -> None:
        assert extract_blockers([]) == []

    def test_sessions_with_no_blockers_returns_empty_list(self) -> None:
        sessions = [
            self._make_handoff_session("feat-a", []),
            self._make_recap_session("feat-b", []),
        ]
        assert extract_blockers(sessions) == []
