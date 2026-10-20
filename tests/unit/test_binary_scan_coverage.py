"""A binary scan that skipped a step says so; a scan that cannot say what ran is `unknown`.

WHY (issue #891). `binary-scan analyze` runs checksec, YARA, strings and a PE/ELF header
parse. The header parse ran "if Python tools available" and checksec differs by OS, so a
scan on a machine without them skipped steps and left no record; ingest then emitted the
findings of the remaining steps as though they were the whole scan. `scan-meta.json` now
carries a `steps` run record, and `parse_binary.py` puts `coverage` (complete | partial |
unknown) and `limitations` on every finding it emits, per the vocabulary of
docs/contracts/pack-capability-contract.md. The findings are flat dicts with no schema
or table behind them (nothing reads them but the other etl scripts, and
`export_dataset.py` writes a fixed column list), so no migration is involved.

Each test runs the real script as a subprocess against a scan directory built in a temp
directory, so the CLI, the file discovery and the stderr summary are all exercised.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ETL = REPO_ROOT / "templates" / "security" / "etl"
PARSER = ETL / "parse_binary.py"
EXAMPLES = REPO_ROOT / "canonical" / "skills" / "security" / "modes" / "binary-scan" / "examples.md"

sys.path.insert(0, str(ETL))
import scan_coverage  # noqa: E402

ALL_STEPS = ("checksec", "yara", "strings", "header_analysis")


def _steps(**status: str) -> list[dict]:
    """Run record for the four steps; `status` overrides one step's status by name."""
    out = []
    for name in ALL_STEPS:
        entry = {"step": name, "status": status.get(name, "ran"), "tool": name}
        if entry["status"] != "ran":
            entry["reason"] = f"{name} is not installed"
        out.append(entry)
    return out


def _scan(root: Path, target: str, date: str, meta: dict | None, *, clean: bool = False) -> Path:
    """One dated scan directory with a checksec result and (optionally) a scan-meta.json."""
    d = root / target / date
    d.mkdir(parents=True)
    checks = {"nx": "yes", "pie": "yes"} if clean else {"nx": "no", "pie": "yes"}
    (d / "checksec.json").write_text(json.dumps({"app.exe": checks}), encoding="utf-8")
    if meta is not None:
        (d / "scan-meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return d


def _parse(scans: Path, tmp: Path, *extra: str) -> tuple[list[dict], dict, str]:
    out = tmp / "findings.json"
    cov = tmp / "coverage.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(PARSER),
            "--client",
            "acme",
            "--scans-dir",
            str(scans),
            "--output",
            str(out),
            "--coverage-output",
            str(cov),
            *extra,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(out.read_text("utf-8")), json.loads(cov.read_text("utf-8")), proc.stderr


# -- the three acceptance cases ---------------------------------------------------------


def test_full_tooling_scan_is_complete(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "app", "2026-10-19", {"schema_version": 1, "steps": _steps()})

    findings, coverage, _ = _parse(scans, tmp_path)

    assert findings, "the fixture has a failing NX check"
    assert {f["coverage"] for f in findings} == {"complete"}
    assert coverage["coverage"] == "complete"
    assert coverage["scans"][0]["skipped_steps"] == []


def test_scan_without_a_tool_is_partial_and_names_the_skipped_step(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(
        scans,
        "app",
        "2026-10-19",
        {"schema_version": 1, "steps": _steps(header_analysis="skipped")},
    )

    findings, coverage, stderr = _parse(scans, tmp_path)

    assert findings
    for f in findings:
        assert f["coverage"] == "partial"
        assert any("header_analysis" in lim and "not installed" in lim for lim in f["limitations"])
    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["skipped_steps"] == ["header_analysis"]
    assert "coverage partial" in stderr and "header_analysis" in stderr


def test_old_scan_meta_with_no_run_record_is_unknown_never_complete(tmp_path: Path):
    scans = tmp_path / "scans"
    # Exactly what binary-scan wrote before the run record existed.
    _scan(
        scans,
        "app",
        "2026-10-19",
        {
            "schema_version": 1,
            "target_type": "binary",
            "scanners": ["checksec", "yara", "strings"],
            "ingested_at": "2026-10-19T00:00:00Z",
        },
    )

    findings, coverage, _ = _parse(scans, tmp_path)

    assert findings
    assert {f["coverage"] for f in findings} == {"unknown"}
    assert coverage["coverage"] == "unknown"
    assert any("no run record" in lim for lim in findings[0]["limitations"])


def test_missing_scan_meta_is_unknown(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "app", "2026-10-19", None)

    findings, coverage, _ = _parse(scans, tmp_path)

    assert {f["coverage"] for f in findings} == {"unknown"}
    assert coverage["coverage"] == "unknown"


# -- what the findings alone cannot show ---------------------------------------------------


def test_a_partial_scan_with_no_findings_is_still_reported_partial(tmp_path: Path):
    """The dangerous case: nothing found, and part of the scan never ran."""
    scans = tmp_path / "scans"
    _scan(
        scans,
        "app",
        "2026-10-19",
        {"schema_version": 1, "steps": _steps(checksec="skipped", header_analysis="skipped")},
        clean=True,
    )

    findings, coverage, _ = _parse(scans, tmp_path)

    assert findings == []
    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["skipped_steps"] == ["checksec", "header_analysis"]


def test_failed_step_is_partial_too(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "app", "2026-10-19", {"steps": _steps(yara="failed")})

    _, coverage, _ = _parse(scans, tmp_path)

    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["skipped_steps"] == ["yara"]


def test_each_scan_directory_is_assessed_on_its_own(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "alpha", "2026-10-19", {"steps": _steps()})
    _scan(scans, "beta", "2026-10-19", {"steps": _steps(header_analysis="skipped")})

    findings, coverage, _ = _parse(scans, tmp_path)

    by_target = {f["target_name"]: f["coverage"] for f in findings}
    assert by_target == {"alpha": "complete", "beta": "partial"}
    assert coverage["coverage"] == "partial"


def test_sample_findings_are_unknown_and_say_they_are_synthetic(tmp_path: Path):
    proc = subprocess.run(
        [sys.executable, str(PARSER), "--client", "acme", "--sample"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    findings = json.loads(proc.stdout)
    assert {f["coverage"] for f in findings} == {"unknown"}
    assert "synthetic" in findings[0]["limitations"][0]


# -- the run-record rules themselves ----------------------------------------------------------


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        (None, "unknown"),
        ({}, "unknown"),
        ({"steps": "not-a-list"}, "unknown"),
        ({"steps": []}, "unknown"),
        # a planned step with no record is not a step that ran
        ({"steps": _steps()[:-1]}, "unknown"),
        # a malformed or unrecognised status is not "ran"
        ({"steps": [*_steps()[:-1], {"step": "header_analysis", "status": "maybe"}]}, "unknown"),
        ({"steps": [*_steps()[:-1], "garbage"]}, "unknown"),
        ({"steps": _steps()}, "complete"),
        ({"steps": _steps(strings="skipped")}, "partial"),
        # skipped outranks unrecorded: it is the more specific, known fact
        ({"steps": [*_steps(strings="skipped")[:-1]]}, "partial"),
    ],
)
def test_assess_rules(meta, expected):
    assert scan_coverage.assess(meta, ALL_STEPS)["coverage"] == expected


def test_overall_partial_beats_unknown_beats_complete():
    c, p, u = ({"coverage": v} for v in ("complete", "partial", "unknown"))
    assert scan_coverage.overall([c, c]) == "complete"
    assert scan_coverage.overall([c, u]) == "unknown"
    assert scan_coverage.overall([c, u, p]) == "partial"
    assert scan_coverage.overall([]) == "unknown"


# -- the mode doc and the parser must agree ------------------------------------------------------


def test_documented_run_record_names_the_steps_the_parser_plans_for():
    """If the doc's schema or step list drifts from PLANNED_STEPS the record is never `complete`."""
    sys.path.insert(0, str(REPO_ROOT))
    import parse_binary

    text = EXAMPLES.read_text(encoding="utf-8")
    assert tuple(parse_binary.PLANNED_STEPS) == ALL_STEPS
    for step in parse_binary.PLANNED_STEPS:
        assert f'{{"step": "{step}"' in text, f"examples.md scan-meta.json omits step {step}"
    assert '"status": "skipped"' in text
    assert "`unknown`" in text
