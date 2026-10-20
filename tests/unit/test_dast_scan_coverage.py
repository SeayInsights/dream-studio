"""A DAST run that continued without Nuclei says so; a run that cannot say what ran is `unknown`.

WHY (issue #891). `dast run` checks "Nuclei is installed ... if missing, continue with ZAP
only", then Step R5 wrote `"scanners": ["zap", "nuclei"]` regardless. The ingested result
read as a two-scanner run. `scan-meta.json` now carries a `steps` run record and
`parse_dast.py` puts `coverage` (complete | partial | unknown) and `limitations` on every
finding, the same way `parse_binary.py` does (see test_binary_scan_coverage.py for the
run-record rules themselves, which live in the shared scan_coverage.py).

Each test runs the real script as a subprocess against a scan directory built in a temp
directory.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


def _steps(nuclei: str = "ran") -> list[dict]:
    nuclei_step = {"step": "nuclei", "status": nuclei, "tool": "nuclei"}
    if nuclei != "ran":
        nuclei_step["reason"] = "nuclei is not installed"
    return [{"step": "zap", "status": "ran", "tool": "zap"}, nuclei_step]


def _scan(
    root: Path, target: str, meta: dict | None, *, nuclei_output: bool, zap_findings: bool = True
) -> Path:
    d = root / target / "2026-10-19"
    d.mkdir(parents=True)
    report = ZAP_REPORT if zap_findings else {**ZAP_REPORT, "site": [{"@name": "x", "alerts": []}]}
    (d / "zap-report.json").write_text(json.dumps(report), encoding="utf-8")
    if nuclei_output:
        (d / "nuclei-output.jsonl").write_text(json.dumps(NUCLEI_LINE) + "\n", encoding="utf-8")
    if meta is not None:
        (d / "scan-meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return d


def _parse(scans: Path, tmp: Path) -> tuple[list[dict], dict, str]:
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


def test_run_with_both_scanners_is_complete(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "web", {"schema_version": 1, "steps": _steps()}, nuclei_output=True)

    findings, coverage, _ = _parse(scans, tmp_path)

    # both scanners' output was parsed
    assert {f["rule_id"].split("-")[1] for f in findings} == {"zap", "nuc"}
    assert {f["coverage"] for f in findings} == {"complete"}
    assert coverage["coverage"] == "complete"


def test_run_without_nuclei_is_partial_and_names_it(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "web", {"schema_version": 1, "steps": _steps("skipped")}, nuclei_output=False)

    findings, coverage, stderr = _parse(scans, tmp_path)

    assert findings
    for f in findings:
        assert f["coverage"] == "partial"
        assert any("nuclei" in lim and "not installed" in lim for lim in f["limitations"])
    assert coverage["scans"][0]["skipped_steps"] == ["nuclei"]
    assert "coverage partial" in stderr and "nuclei" in stderr


def test_old_scan_meta_that_lists_both_scanners_but_no_run_record_is_unknown(tmp_path: Path):
    """The pre-change meta claimed both scanners whether or not Nuclei ran: not evidence."""
    scans = tmp_path / "scans"
    _scan(
        scans,
        "web",
        {"schema_version": 1, "scanners": ["zap", "nuclei"], "target_type": "webapp"},
        nuclei_output=False,
    )

    findings, coverage, _ = _parse(scans, tmp_path)

    assert findings
    assert {f["coverage"] for f in findings} == {"unknown"}
    assert coverage["coverage"] == "unknown"


def test_partial_run_with_no_findings_is_still_reported_partial(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(
        scans,
        "web",
        {"steps": _steps("skipped")},
        nuclei_output=False,
        zap_findings=False,
    )

    findings, coverage, _ = _parse(scans, tmp_path)

    assert findings == []
    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["skipped_steps"] == ["nuclei"]


def test_documented_run_record_names_the_steps_the_parser_plans_for():
    sys.path.insert(0, str(ETL))
    sys.path.insert(0, str(REPO_ROOT))
    import parse_dast

    text = EXAMPLES.read_text(encoding="utf-8")
    assert tuple(parse_dast.PLANNED_STEPS) == ("zap", "nuclei")
    for step in parse_dast.PLANNED_STEPS:
        assert f'{{"step": "{step}"' in text, f"examples.md scan-meta.json omits step {step}"
    assert '"status": "skipped"' in text
