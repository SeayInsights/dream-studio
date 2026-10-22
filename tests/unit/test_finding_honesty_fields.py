"""A finding must say how much of its check was real, and say "unknown" when nobody did.

Today a scan that silently skipped a step looks identical to a complete one. The three
honesty fields (confidence, coverage, limitations) fix that only if an unrecorded value
can never read as a certain one: a default of "complete" or "high" would be a wrong
answer, not a missing one. These tests pin that, and that the value is visible to a
human in the rendered page and not only in JSON.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.findings import Finding, collect_findings
from core.findings.collect import from_audit_markdown, from_guard_log, from_security_events
from core.findings.model import (
    normalize_confidence,
    normalize_coverage,
    normalize_limitations,
)
from core.findings.render import render_findings_html, render_findings_json


def _finding(**kw) -> Finding:
    return Finding(source="s", severity="high", title="t", ref="r", **kw)


# ---------------------------------------------------------------------------
# Defaults never claim certainty
# ---------------------------------------------------------------------------


def test_an_unrecorded_finding_reads_as_unknown_not_certain():
    f = _finding()
    assert f.confidence == "unknown"
    assert f.coverage == "unknown"
    assert f.limitations is None, "None = not recorded; () would claim 'none exist'"


def test_recorded_none_is_distinct_from_not_recorded():
    assert _finding(limitations=()).limitations == ()
    assert _finding(limitations=()).to_dict()["limitations"] == []
    assert _finding().to_dict()["limitations"] is None


@pytest.mark.parametrize("raw", [None, "", "certain", "HIGHEST", 3, object()])
def test_junk_confidence_and_coverage_become_unknown_never_high_or_complete(raw):
    assert normalize_confidence(raw) == "unknown"
    assert normalize_coverage(raw) == "unknown"
    f = _finding(confidence=raw, coverage=raw)
    assert (f.confidence, f.coverage) == ("unknown", "unknown")


@pytest.mark.parametrize(
    "raw,conf",
    [("High", "high"), (" medium ", "medium"), ("LOW", "low")],
)
def test_recognised_confidence_is_kept(raw, conf):
    assert normalize_confidence(raw) == conf


@pytest.mark.parametrize("raw", ["complete", "Partial", "unknown"])
def test_recognised_coverage_is_kept(raw):
    assert normalize_coverage(raw) == raw.lower()


def test_limitations_coercion():
    assert normalize_limitations(None) is None
    assert normalize_limitations("one") == ("one",)
    assert normalize_limitations(["a", " ", "b"]) == ("a", "b")
    assert normalize_limitations(42) is None, "an unusable value is not recorded"
    assert normalize_limitations([]) == (), "a genuinely empty list asserts 'none exist'"
    assert normalize_limitations(()) == ()
    for blank in ("", "   ", ["", " "], [" "]):
        assert normalize_limitations(blank) is None, f"{blank!r} records nothing"


def test_to_dict_carries_all_three_fields():
    d = _finding(confidence="low", coverage="partial", limitations=["no semgrep"]).to_dict()
    assert d["confidence"] == "low"
    assert d["coverage"] == "partial"
    assert d["limitations"] == ["no semgrep"]


def test_json_render_includes_the_fields():
    out = json.loads(
        render_findings_json([_finding(coverage="partial", limitations=["skipped step"])], [])
    )
    row = out["findings"][0]
    assert row["coverage"] == "partial"
    assert row["limitations"] == ["skipped step"]


# ---------------------------------------------------------------------------
# Visible to a human, not only in JSON
# ---------------------------------------------------------------------------


def test_html_shows_partial_coverage_and_the_limitation_text():
    html = render_findings_html(
        [_finding(coverage="partial", confidence="low", limitations=["header parse skipped"])],
        [],
    )
    assert "cov-partial" in html
    assert "header parse skipped" in html
    assert "confidence: low" in html


def test_html_shows_unrecorded_coverage_as_unknown_not_complete():
    html = render_findings_html([_finding()], [])
    assert "cov-unknown" in html
    assert "cov-complete" not in html.split("<tbody>")[1], "unrecorded must not read complete"


def test_html_summary_counts_coverage_by_value():
    html = render_findings_html(
        [
            _finding(coverage="partial"),
            _finding(coverage="partial"),
            _finding(coverage="complete"),
            _finding(),
        ],
        [],
    )
    assert "2 partial" in html and "1 complete" in html and "1 unknown" in html


def test_html_escapes_limitation_text():
    html = render_findings_html([_finding(limitations=["<img src=x onerror=1>"])], [])
    assert "<img src=x" not in html
    assert "&lt;img" in html


# ---------------------------------------------------------------------------
# Producers: populated only where the source recorded it
# ---------------------------------------------------------------------------


def test_security_event_rows_stay_unknown(tmp_path: Path):
    """A security_events table without the honesty columns (a database older than migration
    161) claims nothing for its rows."""
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE security_events (event_id TEXT, event_kind TEXT, project_id TEXT,"
        " file_path TEXT, line_number INTEGER, severity TEXT, title TEXT, body TEXT,"
        " created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO security_events VALUES ('e','finding.recorded','p','a',1,'high','t','b','t')"
    )
    conn.commit()
    conn.close()
    (f,) = from_security_events(db)
    assert (f.confidence, f.coverage, f.limitations) == ("unknown", "unknown", None)


def _guard_log(tmp_path: Path, *rows: dict) -> Path:
    p = tmp_path / "guard-findings.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def test_guard_log_passes_through_only_what_the_line_recorded(tmp_path: Path):
    log = _guard_log(
        tmp_path,
        {
            "severity": "high",
            "description": "recorded",
            "confidence": "medium",
            "coverage": "partial",
            "limitations": ["tool missing"],
        },
        {"severity": "high", "description": "bare"},
    )
    recorded, bare = from_guard_log(log)
    assert (recorded.confidence, recorded.coverage) == ("medium", "partial")
    assert recorded.limitations == ("tool missing",)
    assert (bare.confidence, bare.coverage, bare.limitations) == ("unknown", "unknown", None)


def test_guard_log_off_vocabulary_values_do_not_become_certain(tmp_path: Path):
    log = _guard_log(
        tmp_path, {"severity": "high", "description": "x", "confidence": "sure", "coverage": "all"}
    )
    (f,) = from_guard_log(log)
    assert (f.confidence, f.coverage) == ("unknown", "unknown")


def _files_db(tmp_path: Path, content: str) -> Path:
    db = tmp_path / "files.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE ds_files (file_id TEXT, project_id TEXT, category TEXT, name TEXT,"
        " version INTEGER, content TEXT, created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO ds_files VALUES ('f','p','planning','milestones/m/security-audit.md',1,?,'t')",
        (content,),
    )
    conn.commit()
    conn.close()
    return db


def test_a_blocker_recovered_from_prose_records_that_limitation(tmp_path: Path):
    (f,) = from_audit_markdown(_files_db(tmp_path, "Verdict: BLOCKED, the scan never completed."))
    assert f.blocking
    assert f.limitations and "prose" in f.limitations[0]
    assert f.coverage == "unknown", "a limitation does not by itself imply coverage"


def test_a_blocker_recovered_from_prose_beside_parsed_lines_records_it_too(tmp_path: Path):
    """Parsed INFO lines do not change how the blocking verdict itself was obtained."""
    found = from_audit_markdown(
        _files_db(tmp_path, "## Findings\n- INFO: minor\n\nVerdict: BLOCKED overall.\n")
    )
    (blocker,) = [f for f in found if f.blocking]
    assert blocker.limitations and "prose" in blocker.limitations[0]


def test_parsed_audit_lines_stay_unknown(tmp_path: Path):
    found = from_audit_markdown(_files_db(tmp_path, "## Findings\n- INFO: something minor\n"))
    assert found
    for f in found:
        assert (f.confidence, f.coverage, f.limitations) == ("unknown", "unknown", None)


def test_collect_findings_end_to_end_keeps_honesty_fields(tmp_path: Path):
    log = _guard_log(tmp_path, {"severity": "high", "description": "x", "coverage": "partial"})
    findings, _ = collect_findings(guard_log=log)
    assert findings[0].coverage == "partial"
