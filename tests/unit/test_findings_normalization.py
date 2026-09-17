"""Findings from three incompatible producers must read as one shape.

Before this, "a finding" existed as SQL rows (security_events), as English prose
in markdown artifacts whose blocking status was recovered by regex, and as a
JSONL log nothing read. No surface could show them together, so answering "what
was found, and where?" required knowing which of the three to look in first.

The tests below pin the two things that make the normalisation trustworthy:
nothing is silently dropped, and a source that could not be read is reported as
failed rather than contributing a quiet zero.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.findings import Finding, collect_findings, normalize_severity, summarize
from core.findings.collect import from_audit_markdown, from_guard_log, from_security_events
from core.findings.render import render_findings_html

# ---------------------------------------------------------------------------
# Fixtures — the three real shapes
# ---------------------------------------------------------------------------


@pytest.fixture
def authority_db(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE security_events (event_id TEXT, event_kind TEXT, project_id TEXT,"
        " file_path TEXT, line_number INTEGER, severity TEXT, title TEXT, body TEXT,"
        " created_at TEXT, cwe_id TEXT, owasp_category TEXT, cve_id TEXT,"
        " vuln_class TEXT, scanner_type TEXT)"
    )
    conn.executemany(
        "INSERT INTO security_events (event_id, event_kind, project_id, file_path,"
        " line_number, severity, title, body, created_at, vuln_class)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (
                "e1",
                "finding.recorded",
                "p1",
                "a.ts",
                21,
                "high",
                "CSP unsafe-eval",
                "body",
                "t",
                "x",
            ),
            ("e2", "finding.recorded", "p1", "b.py", 5, "low", "long function", "body", "t", "y"),
            ("e3", "finding.resolved", "p1", "c.py", 9, "high", "already fixed", "body", "t", "z"),
        ],
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def files_db(tmp_path: Path) -> Path:
    db = tmp_path / "files.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE ds_files (file_id TEXT, project_id TEXT, category TEXT, name TEXT,"
        " version INTEGER, content TEXT, created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO ds_files VALUES (?,?,?,?,?,?,?)",
        (
            "f1",
            "p1",
            "planning",
            "milestones/m1/security-audit.md",
            1,
            "# Security Audit\n\n## Findings\n"
            "- **BLOCKED — secrets committed to the repo.** Rotate immediately.\n"
            "- **INFO — innerHTML used on authority strings.** Low risk.\n"
            "- PASS: no injection in the new DB write\n",
            "t",
        ),
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def guard_log(tmp_path: Path) -> Path:
    p = tmp_path / "guard-findings.jsonl"
    p.write_text(
        json.dumps(
            {
                "project_id": "p1",
                "rule_id": "guard-001",
                "severity": "critical",
                "description": "Pattern attempts to override prior AI instructions",
                "matched_text": "ignore all previous instructions",
                "line_number": 3,
                "target_path": "x/y.md",
            }
        )
        + "\n"
        + "not json at all\n"
        + json.dumps({"project_id": "p1", "severity": "weird-value", "description": "odd"})
        + "\n",
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# Severity normalisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("CRITICAL", "critical"),
        ("Blocker", "critical"),
        ("warning", "medium"),
        ("error", "high"),
        ("passed", "pass"),
        ("", "info"),
        (None, "info"),
        ("something-nobody-defined", "info"),
    ],
)
def test_severity_vocabularies_converge(raw, expected):
    assert normalize_severity(raw) == expected


def test_unknown_severity_is_kept_not_dropped():
    """Dropping an unrecognised severity would repeat the bug this module fixes."""
    assert normalize_severity("nonsense") == "info"


# ---------------------------------------------------------------------------
# Per-source adapters
# ---------------------------------------------------------------------------


def test_security_events_adapter_reads_only_recorded_findings(authority_db: Path):
    found = from_security_events(authority_db)
    titles = {f.title for f in found}
    assert "CSP unsafe-eval" in titles
    assert "already fixed" not in titles, "finding.resolved is not an open finding"
    high = next(f for f in found if f.title == "CSP unsafe-eval")
    assert high.severity == "high"
    assert high.location == "a.ts:21"
    assert high.blocking is True


def test_markdown_adapter_extracts_labelled_findings(files_db: Path):
    found = from_audit_markdown(files_db)
    by_sev = {f.severity for f in found}
    assert "critical" in by_sev, "a BLOCKED line must normalise to critical"
    assert "info" in by_sev
    assert "pass" in by_sev
    blocked = [f for f in found if f.blocking]
    assert blocked, "the BLOCKED finding must be marked blocking"
    assert "secrets committed" in blocked[0].detail


def test_markdown_adapter_does_not_double_report_a_parsed_blocker(files_db: Path):
    """The fallback exists for unparsed blockers, not as a duplicate."""
    found = from_audit_markdown(files_db)
    blocking = [f for f in found if f.blocking]
    assert len(blocking) == 1, [f.title for f in blocking]


def test_markdown_adapter_surfaces_an_unparsed_blocker(tmp_path: Path):
    """A blocking verdict that the line regex misses must NOT be lost."""
    db = tmp_path / "f.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE ds_files (file_id TEXT, project_id TEXT, category TEXT, name TEXT,"
        " version INTEGER, content TEXT, created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO ds_files VALUES (?,?,?,?,?,?,?)",
        (
            "f",
            "p",
            "planning",
            "milestones/m/security-audit.md",
            1,
            "Verdict: BLOCKED because the scan never completed.",
            "t",
        ),
    )
    conn.commit()
    conn.close()

    found = from_audit_markdown(db)
    assert any(f.blocking for f in found), "an unparsed BLOCKED verdict must still surface"


def test_negated_blocked_summary_is_not_a_blocker(tmp_path: Path):
    """'No BLOCKED findings' must not be read as a blocker."""
    db = tmp_path / "f.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE ds_files (file_id TEXT, project_id TEXT, category TEXT, name TEXT,"
        " version INTEGER, content TEXT, created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO ds_files VALUES (?,?,?,?,?,?,?)",
        (
            "f",
            "p",
            "planning",
            "milestones/m/security-audit.md",
            1,
            "## Findings\n- PASS: clean scan\n\nNo BLOCKED findings.\n",
            "t",
        ),
    )
    conn.commit()
    conn.close()
    assert not any(f.blocking for f in from_audit_markdown(db))


def test_guard_log_adapter_skips_malformed_lines(guard_log: Path):
    found = from_guard_log(guard_log)
    assert len(found) == 2, "the unparseable line must be skipped, the rest kept"
    crit = next(f for f in found if f.severity == "critical")
    assert crit.extra["rule_id"] == "guard-001"
    assert crit.location == "x/y.md:3"


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


def test_collect_merges_all_three_sources(authority_db, files_db, guard_log):
    findings, sources = collect_findings(
        db_path=authority_db, files_db=files_db, guard_log=guard_log
    )
    assert {s["source"] for s in sources} == {"security_event", "audit_markdown", "guard_log"}
    assert all(s["status"] == "ok" for s in sources), sources
    assert {f.source for f in findings} == {"security_event", "audit_markdown", "guard_log"}


def test_collect_sorts_most_severe_first(authority_db, files_db, guard_log):
    findings, _ = collect_findings(db_path=authority_db, files_db=files_db, guard_log=guard_log)
    assert findings[0].severity == "critical"
    ranks = [f.sort_key()[0] for f in findings]
    assert ranks == sorted(ranks), "findings must be ordered most-severe-first"


def test_an_absent_source_is_reported_not_silently_zero(authority_db, tmp_path):
    _findings, sources = collect_findings(
        db_path=authority_db,
        files_db=tmp_path / "nope.db",
        guard_log=tmp_path / "nope.jsonl",
    )
    statuses = {s["source"]: s["status"] for s in sources}
    assert statuses["audit_markdown"] == "absent"
    assert statuses["guard_log"] == "absent"
    assert statuses["security_event"] == "ok"


def test_a_broken_source_is_reported_as_failed_not_as_empty(tmp_path, files_db, guard_log):
    """'No findings' and 'could not look' must never render identically."""
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"this is definitely not sqlite")
    _findings, sources = collect_findings(db_path=corrupt, files_db=files_db, guard_log=guard_log)
    sec = next(s for s in sources if s["source"] == "security_event")
    assert sec["status"] == "failed", sec
    assert sec.get("error")


def test_one_broken_source_does_not_hide_the_others(tmp_path, files_db, guard_log):
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"nope")
    findings, _ = collect_findings(db_path=corrupt, files_db=files_db, guard_log=guard_log)
    assert findings, "the readable sources must still contribute"


def test_summarize_counts_severity_and_blocking():
    findings = [
        Finding(source="s", severity="critical", title="a", ref="1", blocking=True),
        Finding(source="s", severity="low", title="b", ref="2"),
    ]
    s = summarize(findings)
    assert s["total"] == 2 and s["blocking"] == 1 and s["critical"] == 1


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_rendered_page_is_self_contained():
    """It opens in VS Code's Simple Browser, which may have no network."""
    html = render_findings_html(
        [Finding(source="s", severity="high", title="t", ref="r")],
        [{"source": "s", "status": "ok", "count": 1}],
    )
    assert "src=" not in html and "href=" not in html, "no external resource references"
    assert "<style>" in html and "<script>" in html, "CSS and JS must be inline"


def test_rendered_page_escapes_finding_text():
    html = render_findings_html(
        [Finding(source="s", severity="high", title="<script>alert(1)</script>", ref="r")],
        [],
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_rendered_page_reports_a_failed_source():
    html = render_findings_html(
        [], [{"source": "security_event", "status": "failed", "count": 0, "error": "boom"}]
    )
    assert "FAILED" in html and "boom" in html


def test_rendered_page_handles_no_findings():
    html = render_findings_html([], [])
    assert "No findings recorded." in html


# ---------------------------------------------------------------------------
# Encoding repair. Asserted by CODEPOINT — a cp1252 console misrepresents this
# in both directions, so terminal output cannot be trusted here.
# ---------------------------------------------------------------------------


def test_double_encoded_text_is_repaired():
    """U+00E2 U+20AC U+201D is an em dash that went through a cp1252 round trip."""
    from core.findings.collect import _demojibake

    broken = "Security Audit \u00e2\u20ac\u201d Dream Studio"
    fixed = _demojibake(broken)
    assert "\u2014" in fixed, [hex(ord(c)) for c in fixed]
    assert "\u00e2" not in fixed


@pytest.mark.parametrize(
    "text",
    [
        "Security Audit \u2014 Dream Studio",  # already-correct em dash
        "plain ascii only",
        "caf\u00e9 na\u00efve",  # accented Latin
        "\u4e2d\u6587 \u2615",  # CJK + emoji: cp1252 cannot encode these
        "",
    ],
    ids=["em-dash", "ascii", "latin1", "cjk-emoji", "empty"],
)
def test_correct_text_is_never_altered(text):
    """Repair must be a no-op on anything not double-encoded."""
    from core.findings.collect import _demojibake

    assert _demojibake(text) == text


def test_repair_runs_on_markdown_content(files_db):
    """The adapter applies the repair, not just the helper in isolation."""
    from core.findings.collect import from_audit_markdown

    for f in from_audit_markdown(files_db):
        assert "\u00e2\u20ac" not in f.title + f.detail, f
