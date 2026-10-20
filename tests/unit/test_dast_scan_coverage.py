"""A DAST run that continued without Nuclei says so; a run that cannot say what ran is `unknown`.

WHY (issue #891). `dast run` checks "Nuclei is installed ... if missing, continue with ZAP
only", then Step R5 wrote `"scanners": ["zap", "nuclei"]` regardless. The ingested result
read as a two-scanner run. `scan-meta.json` now carries a `steps` run record and
`parse_dast.py` puts `coverage` (complete | partial | unknown) and `limitations` on every
finding, the same way `parse_binary.py` does (see test_binary_scan_coverage.py for the
shared rules, which live in scan_coverage.py, and for the malformed-record fuzz).

`complete` needs BOTH the run record saying a scanner ran AND the parser having read a
result for it: a missing report, an empty or malformed ZAP report, or a Nuclei file with a
malformed line leaves the step unread and the scan `partial`.

Each test runs the real script as a subprocess against a scan directory built in a temp
directory.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ETL = REPO_ROOT / "templates" / "security" / "etl"
PARSER = ETL / "parse_dast.py"
EXAMPLES = REPO_ROOT / "canonical" / "skills" / "security" / "modes" / "dast" / "examples.md"

ZAP_REPORT = {
    "@version": "2.14.0",
    "site": [
        {
            "@name": "https://app.example.test",
            "alerts": [
                {
                    "pluginid": "10010",
                    "riskcode": "1",
                    "name": "Cookie No HttpOnly Flag",
                    "instances": [{"uri": "https://app.example.test/login"}],
                }
            ],
        }
    ],
}
NUCLEI_LINE = {
    "template-id": "exposed-panel",
    "info": {"name": "Exposed panel", "severity": "medium"},
    "host": "https://app.example.test",
    "matched-at": "https://app.example.test/admin",
}
ALL_STEPS = ("zap", "nuclei")


def _steps(**status: str) -> list[dict]:
    out = []
    for name in ALL_STEPS:
        entry = {"step": name, "status": status.get(name, "ran"), "tool": name}
        if entry["status"] != "ran":
            entry["reason"] = f"{name} is not installed"
        out.append(entry)
    return out


def _scan(
    root: Path,
    target: str,
    meta: object,
    *,
    zap: str | None = "findings",
    nuclei: str | None = "findings",
) -> Path:
    """A scan dir. `zap`: findings | clean | empty | None (no file). `nuclei`: findings |
    empty (a result: found nothing) | malformed | None (no file)."""
    d = root / target / "2026-10-19"
    d.mkdir(parents=True)
    if zap == "findings":
        (d / "zap-report.json").write_text(json.dumps(ZAP_REPORT), encoding="utf-8")
    elif zap == "clean":
        clean = {**ZAP_REPORT, "site": [{"@name": "x", "alerts": []}]}
        (d / "zap-report.json").write_text(json.dumps(clean), encoding="utf-8")
    elif zap == "empty":
        (d / "zap-report.json").write_text("", encoding="utf-8")
    if nuclei == "findings":
        (d / "nuclei-output.jsonl").write_text(json.dumps(NUCLEI_LINE) + "\n", encoding="utf-8")
    elif nuclei == "empty":
        (d / "nuclei-output.jsonl").write_text("", encoding="utf-8")
    elif nuclei == "malformed":
        (d / "nuclei-output.jsonl").write_text("{not json\n", encoding="utf-8")
    if isinstance(meta, str):
        (d / "scan-meta.json").write_text(meta, encoding="utf-8")
    elif meta is not None:
        (d / "scan-meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return d


def _run(scans: Path, tmp: Path, *, rc: int = 0) -> tuple[list[dict] | None, dict | None, str]:
    out = tmp / "findings.json"
    cov = tmp / "coverage.json"
    for p in (out, cov):
        p.unlink(missing_ok=True)
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
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp,
        timeout=120,
    )
    assert proc.returncode == rc, proc.stdout + proc.stderr
    findings = json.loads(out.read_text("utf-8")) if out.exists() else None
    coverage = json.loads(cov.read_text("utf-8")) if cov.exists() else None
    return findings, coverage, proc.stderr


def test_run_with_both_scanners_read_is_complete(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "web", {"schema_version": 1, "steps": _steps()})

    findings, coverage, _ = _run(scans, tmp_path)

    assert {f["rule_id"].split("-")[1] for f in findings} == {"zap", "nuc"}
    assert {f["coverage"] for f in findings} == {"complete"}
    assert coverage["coverage"] == "complete"
    assert coverage["scans"][0]["steps_read"] == list(ALL_STEPS)


def test_run_without_nuclei_is_partial_and_names_it(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "web", {"schema_version": 1, "steps": _steps(nuclei="skipped")}, nuclei=None)

    findings, coverage, stderr = _run(scans, tmp_path)

    assert findings
    for f in findings:
        assert f["coverage"] == "partial"
        assert any("nuclei" in lim and "not installed" in lim for lim in f["limitations"])
    assert coverage["scans"][0]["skipped_steps"] == ["nuclei"]
    assert "coverage partial" in stderr and "nuclei" in stderr


def test_old_scan_meta_that_lists_both_scanners_but_no_run_record_is_unknown(tmp_path: Path):
    """The pre-change meta claimed both scanners whether or not Nuclei ran: not evidence."""
    scans = tmp_path / "scans"
    _scan(scans, "web", {"schema_version": 1, "scanners": ["zap", "nuclei"]}, nuclei=None)

    findings, coverage, _ = _run(scans, tmp_path)

    assert findings
    assert {f["coverage"] for f in findings} == {"unknown"}
    assert coverage["coverage"] == "unknown"


# -- defect A: `ran` in the record is not the same as "the parser read it" ----------------------


def test_zap_recorded_ran_but_report_absent_is_partial(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "web", {"steps": _steps()}, zap=None)

    findings, coverage, _ = _run(scans, tmp_path)

    assert {f["coverage"] for f in findings} == {"partial"}
    assert coverage["scans"][0]["unread_steps"] == ["zap"]
    assert any("recorded as ran but no zap result" in lim for lim in coverage["scans"][0]["limitations"])


def test_nuclei_recorded_ran_but_output_absent_is_partial(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "web", {"steps": _steps()}, nuclei=None)

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["unread_steps"] == ["nuclei"]


def test_empty_zap_report_is_unparseable_and_partial(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "web", {"steps": _steps()}, zap="empty")

    findings, coverage, stderr = _run(scans, tmp_path)

    assert "Failed to parse zap-report.json" in stderr
    assert coverage["scans"][0]["unread_steps"] == ["zap"]
    assert {f["coverage"] for f in findings} == {"partial"}


@pytest.mark.parametrize(
    "content",
    [
        "{not json\n",  # not JSON at all
        "[1, 2]\n",  # JSON, but not an object
        '"a string"\n',
        "42\n",
        json.dumps(NUCLEI_LINE) + "\n{truncated\n",  # a good line then a bad one
    ],
    ids=["not-json", "array", "string", "number", "good-then-bad"],
)
def test_nuclei_file_with_a_line_that_is_not_a_json_object_is_not_a_read_result(
    content: str, tmp_path: Path
):
    scans = tmp_path / "scans"
    d = _scan(scans, "web", {"steps": _steps()}, nuclei=None)
    (d / "nuclei-output.jsonl").write_text(content, encoding="utf-8")

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["scans"][0]["unread_steps"] == ["nuclei"]


def test_nuclei_that_found_nothing_leaves_an_empty_file_and_is_read(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "web", {"steps": _steps()}, nuclei="empty")

    findings, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "complete"
    assert {f["rule_id"].split("-")[1] for f in findings} == {"zap"}


def test_failed_scanner_is_partial(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "web", {"steps": _steps(zap="failed")}, zap=None)

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["skipped_steps"] == ["zap"]


def test_ran_without_a_tool_is_not_a_usable_record(tmp_path: Path):
    scans = tmp_path / "scans"
    steps = _steps()
    del steps[1]["tool"]
    _scan(scans, "web", {"steps": steps})

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "unknown"


# -- defect B: a malformed run record never costs a finding --------------------------------------


@pytest.mark.parametrize(
    "steps",
    [
        [{"step": ["x"], "status": "ran"}],
        [{"step": "zap", "status": ["ran"], "tool": {"x": 1}}],
        [None, 1, "x", [[]]],
        "not a list",
        [{"step": "nuclei", "status": "ran", "tool": "t" * 100_000}],
    ],
)
def test_malformed_run_record_loses_no_findings(steps, tmp_path: Path):
    healthy = tmp_path / "healthy"
    healthy.mkdir()
    _scan(healthy / "scans", "web", {"steps": _steps()})
    expected, _, _ = _run(healthy / "scans", healthy)

    scans = tmp_path / "scans"
    _scan(scans, "web", {"steps": steps})
    findings, coverage, _ = _run(scans, tmp_path)

    assert sorted(f["fingerprint"] for f in findings) == sorted(f["fingerprint"] for f in expected)
    assert coverage["coverage"] in {"partial", "unknown"}
    assert coverage["scans"]


# -- defect C: the sidecar is written before any non-zero exit ---------------------------------


def test_every_scanner_skipped_and_no_result_files_still_writes_the_sidecar(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "web", {"steps": _steps(zap="skipped", nuclei="skipped")}, zap=None, nuclei=None)

    findings, coverage, stderr = _run(scans, tmp_path, rc=1)

    assert findings is None
    assert "No ZAP/Nuclei result files" in stderr
    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["skipped_steps"] == ["zap", "nuclei"]


def test_empty_and_missing_scan_directories_write_an_unknown_sidecar(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    _, coverage, _ = _run(empty, tmp_path, rc=1)
    assert coverage["coverage"] == "unknown"

    _, coverage, stderr = _run(tmp_path / "missing", tmp_path, rc=1)
    assert "scans directory not found" in stderr
    assert coverage["coverage"] == "unknown"


def test_partial_run_with_no_findings_is_still_reported_partial(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "web", {"steps": _steps(nuclei="skipped")}, zap="clean", nuclei=None)

    findings, coverage, _ = _run(scans, tmp_path)

    assert findings == []
    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["skipped_steps"] == ["nuclei"]


def test_documented_run_record_names_the_steps_the_parser_plans_for():
    sys.path.insert(0, str(ETL))
    sys.path.insert(0, str(REPO_ROOT))
    import parse_dast

    text = EXAMPLES.read_text(encoding="utf-8")
    assert tuple(parse_dast.PLANNED_STEPS) == ALL_STEPS
    for step in parse_dast.PLANNED_STEPS:
        assert f'{{"step": "{step}"' in text, f"examples.md scan-meta.json omits step {step}"
    assert '"status": "skipped"' in text
    # the template must not hard-code `ran`: a scanner that errored is `failed`
    assert '"status": "ran"' not in text
    assert "`failed`" in text
