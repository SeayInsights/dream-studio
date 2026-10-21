"""`scan ingest` records a workflow run that did not succeed, and parse_sarif carries it.

WHY (issue #895 item 5). The ingest step downloaded the artifacts of the latest
`security-scan.yml` run even when that run did not conclude `success`, and said so only in
chat ("findings may be partial"). `scan-meta.json` kept no trace of it, there was no
per-scanner record (did semgrep run? did bandit?), and `parse_sarif.py` stamped no coverage
at all, so a partial scan reached the dashboards as a complete one.

The rule these tests hold, shared with binary-scan and dast through scan_coverage.py:

  * `scan-meta.json` carries the same run record (`steps`: one entry per scanner, `ran` |
    `skipped` | `failed`) and a `run` object with the run's `conclusion`;
  * a run whose conclusion is not `success` is `partial` and says why, whatever the steps
    say; a `run` with no readable conclusion is `unknown`;
  * a scan directory with no run record (a local-file ingest) is `unknown`, never complete;
  * `complete` still needs a result read for every planned scanner.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ETL = REPO_ROOT / "templates" / "security" / "etl"
PARSER = ETL / "parse_sarif.py"
SCAN_SKILL = REPO_ROOT / "canonical" / "skills" / "security" / "modes" / "scan" / "SKILL.md"
SCAN_EXAMPLES = REPO_ROOT / "canonical" / "skills" / "security" / "modes" / "scan" / "examples.md"

sys.path.insert(0, str(ETL))
import parse_sarif  # noqa: E402
import scan_coverage  # noqa: E402

SARIF = {
    "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
    "runs": [
        {
            "tool": {"driver": {"name": "semgrep", "rules": []}},
            "results": [
                {
                    "ruleId": "x.sqli",
                    "level": "error",
                    "message": {"text": "sql injection"},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": "app/db.py"},
                                "region": {"startLine": 7},
                            }
                        }
                    ],
                }
            ],
        }
    ],
}
BANDIT = {
    "errors": [],
    "generated_at": "2026-10-20T00:00:00Z",
    "metrics": {},
    "results": [
        {
            "test_id": "B608",
            "issue_severity": "HIGH",
            "filename": "app/db.py",
            "line_number": 9,
            "issue_text": "possible sql injection",
        }
    ],
}


def _steps(**status: str) -> list[dict]:
    out = []
    for name in ("semgrep", "bandit"):
        entry = {"step": name, "status": status.get(name, "ran"), "tool": name}
        if entry["status"] != "ran":
            entry["reason"] = f"{name} job concluded {entry['status']}"
        out.append(entry)
    return out


def _scan(root: Path, meta: object, files: dict[str, object] | None = None) -> Path:
    d = root / "repo-a" / "2026-10-20"
    d.mkdir(parents=True)
    if meta is not None:
        (d / "scan-meta.json").write_text(json.dumps(meta), encoding="utf-8")
    for name, content in (files or {"semgrep.sarif": SARIF, "bandit.json": BANDIT}).items():
        text = content if isinstance(content, str) else json.dumps(content)
        (d / name).write_text(text, encoding="utf-8")
    return d


def _run(scan_dir: Path, tmp_path: Path) -> tuple[list[dict], dict, str, int]:
    cov = tmp_path / "coverage.json"
    out = tmp_path / "findings.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(PARSER),
            "--client",
            "c",
            "--scans-dir",
            str(scan_dir),
            "--output",
            str(out),
            "--coverage-output",
            str(cov),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    findings = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    coverage = json.loads(cov.read_text(encoding="utf-8")) if cov.exists() else {}
    return findings, coverage, proc.stderr, proc.returncode


def _meta(conclusion: object = "success", steps: object = None, **extra: object) -> dict:
    meta = {
        "schema_version": 1,
        "source": "github-actions",
        "planned_steps": ["semgrep", "bandit"],
        "run": {"run_id": "123", "status": "completed", "conclusion": conclusion},
        "steps": _steps() if steps is None else steps,
    }
    meta.update(extra)
    return meta


# -- the rule in scan_coverage.assess -------------------------------------------------------------


def test_a_run_that_did_not_succeed_is_partial_even_when_every_step_ran() -> None:
    report = scan_coverage.assess(_meta("failure"), ("semgrep", "bandit"), {"semgrep", "bandit"})
    assert report["coverage"] == "partial"
    assert any("concluded failure" in x for x in report["limitations"])


@pytest.mark.parametrize("conclusion", ["cancelled", "timed_out", "neutral", "skipped"])
def test_every_non_success_conclusion_is_partial(conclusion: str) -> None:
    report = scan_coverage.assess(_meta(conclusion), ("semgrep", "bandit"), {"semgrep", "bandit"})
    assert report["coverage"] == "partial"
    assert any(f"concluded {conclusion}" in x for x in report["limitations"])


def test_a_successful_run_with_every_step_read_is_complete() -> None:
    report = scan_coverage.assess(_meta("success"), ("semgrep", "bandit"), {"semgrep", "bandit"})
    assert report["coverage"] == "complete"
    assert report["limitations"] == []


@pytest.mark.parametrize("run", [{}, {"conclusion": None}, {"conclusion": ""}, "failure", 3])
def test_a_run_record_with_no_readable_conclusion_is_unknown_never_complete(run: object) -> None:
    meta = _meta()
    meta["run"] = run
    report = scan_coverage.assess(meta, ("semgrep", "bandit"), {"semgrep", "bandit"})
    assert report["coverage"] == "unknown"
    assert any("conclusion" in x for x in report["limitations"])


def test_a_meta_without_a_run_object_is_judged_by_its_steps_alone() -> None:
    meta = _meta()
    del meta["run"]  # binary-scan and dast do not record one
    assert scan_coverage.assess(meta, ("semgrep", "bandit"), {"semgrep", "bandit"})["coverage"] == (
        "complete"
    )


def test_a_failed_run_with_no_steps_is_still_named_partial() -> None:
    meta = {"run": {"conclusion": "failure"}}
    report = scan_coverage.assess(meta, ("semgrep",), set())
    assert report["coverage"] == "partial"
    assert any("concluded failure" in x for x in report["limitations"])


def test_a_hostile_conclusion_is_bounded_and_printable() -> None:
    report = scan_coverage.assess(
        _meta("fail\x1b[31m" + "x" * 5000), ("semgrep", "bandit"), {"semgrep", "bandit"}
    )
    text = " ".join(report["limitations"])
    assert "\x1b" not in text and len(text) < 1000


# -- the parser: coverage on every finding and in the sidecar -----------------------------------


def test_a_failed_run_reaches_the_findings_and_the_sidecar(tmp_path: Path) -> None:
    d = _scan(tmp_path / "scans", _meta("failure"))
    findings, coverage, _, code = _run(d, tmp_path)
    assert code == 0
    assert findings and {f["coverage"] for f in findings} == {"partial"}
    assert all(any("concluded failure" in x for x in f["limitations"]) for f in findings)
    assert coverage["coverage"] == "partial"


def test_a_per_scanner_failure_is_named(tmp_path: Path) -> None:
    d = _scan(
        tmp_path / "scans",
        _meta("success", steps=_steps(bandit="failed")),
        {"semgrep.sarif": SARIF},
    )
    findings, coverage, _, _ = _run(d, tmp_path)
    assert {f["coverage"] for f in findings} == {"partial"}
    limits = " ".join(coverage["scans"][0]["limitations"])
    assert "bandit" in limits and "failed" in limits and "job concluded failed" in limits


def test_a_clean_successful_run_is_complete(tmp_path: Path) -> None:
    d = _scan(tmp_path / "scans", _meta("success"))
    findings, coverage, stderr, _ = _run(d, tmp_path)
    assert findings
    assert {f["coverage"] for f in findings} == {"complete"}, coverage
    assert coverage["coverage"] == "complete"
    assert all(f["limitations"] == [] for f in findings)  # scan-meta.json is not a "result"
    assert "scan-meta.json" not in stderr.replace("scan-meta.json is missing", "")
    assert coverage["scans"][0]["limitations"] == []


def test_a_recorded_step_the_plan_does_not_list_still_counts(tmp_path: Path) -> None:
    meta = _meta("success", steps=_steps(bandit="failed"))
    del meta["planned_steps"]
    d = _scan(tmp_path / "scans", meta, {"semgrep.sarif": SARIF})
    findings, coverage, _, _ = _run(d, tmp_path)
    assert {f["coverage"] for f in findings} == {"partial"}
    assert "bandit" in " ".join(coverage["scans"][0]["limitations"])


def test_a_planned_scanner_with_no_result_is_partial_and_named(tmp_path: Path) -> None:
    d = _scan(tmp_path / "scans", _meta("success"), {"semgrep.sarif": SARIF})
    findings, coverage, _, _ = _run(d, tmp_path)
    assert {f["coverage"] for f in findings} == {"partial"}
    assert coverage["scans"][0]["unread_steps"] == ["bandit"]


def test_a_local_file_ingest_has_no_run_record_and_reads_unknown(tmp_path: Path) -> None:
    meta = {"schema_version": 1, "source": "local-file", "files": ["semgrep.sarif"]}
    d = _scan(tmp_path / "scans", meta, {"semgrep.sarif": SARIF})
    findings, coverage, _, _ = _run(d, tmp_path)
    assert {f["coverage"] for f in findings} == {"unknown"}
    assert "run record" in " ".join(coverage["scans"][0]["limitations"])


def test_no_scan_meta_at_all_is_unknown(tmp_path: Path) -> None:
    d = _scan(tmp_path / "scans", None, {"semgrep.sarif": SARIF})
    findings, _, _, _ = _run(d, tmp_path)
    assert {f["coverage"] for f in findings} == {"unknown"}


def test_a_scanner_output_the_parser_cannot_read_is_named_not_silently_dropped(
    tmp_path: Path,
) -> None:
    meta = _meta(
        "success", steps=_steps() + [{"step": "npm-audit", "status": "ran", "tool": "npm"}]
    )
    meta["planned_steps"] = ["semgrep", "bandit", "npm-audit"]
    d = _scan(
        tmp_path / "scans",
        meta,
        {
            "semgrep.sarif": SARIF,
            "bandit.json": BANDIT,
            "npm-audit-results.json": {"auditReportVersion": 2, "vulnerabilities": {}},
        },
    )
    findings, coverage, _, _ = _run(d, tmp_path)
    scan = coverage["scans"][0]
    assert scan["coverage"] == "partial"
    assert "npm-audit" in scan["unread_steps"]
    assert any("npm-audit-results.json" in x for x in scan["limitations"])
    assert findings and {f["coverage"] for f in findings} == {"partial"}


def test_an_empty_bandit_result_is_a_read_result_not_a_missing_one(tmp_path: Path) -> None:
    empty = {"errors": [], "generated_at": "2026-10-20T00:00:00Z", "metrics": {}, "results": []}
    d = _scan(tmp_path / "scans", _meta("success"), {"semgrep.sarif": SARIF, "bandit.json": empty})
    _, coverage, _, _ = _run(d, tmp_path)
    assert coverage["scans"][0]["unread_steps"] == []
    assert coverage["coverage"] == "complete"


def test_a_corrupt_result_is_named_and_the_others_still_count(tmp_path: Path) -> None:
    d = _scan(
        tmp_path / "scans",
        _meta("success"),
        {"semgrep.sarif": SARIF, "bandit.json": "{ not json"},
    )
    findings, coverage, _, _ = _run(d, tmp_path)
    scan = coverage["scans"][0]
    assert findings and scan["unread_steps"] == ["bandit"]
    assert any("bandit.json could not be read" in x for x in scan["limitations"])


def test_the_repo_name_comes_from_the_scan_directory_not_the_scanner_file_name(
    tmp_path: Path,
) -> None:
    d = _scan(tmp_path / "scans", _meta("success"))
    findings, _, _, _ = _run(d, tmp_path)
    assert {f["repo"] for f in findings} == {"repo-a"}


def test_a_scanner_suffixed_file_name_still_names_the_repo(tmp_path: Path) -> None:
    d = _scan(tmp_path / "scans", None, {"vendor-portal-semgrep.sarif": SARIF})
    findings, _, _, _ = _run(d, tmp_path)
    assert {f["repo"] for f in findings} == {"vendor-portal"}


def test_sample_mode_is_marked_unknown(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(PARSER), "--sample", "--client", "c"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    findings = json.loads(proc.stdout)
    assert {f["coverage"] for f in findings} == {"unknown"}


# -- the documented record is the record the parser reads -----------------------------------------


def _documented_meta(conclusion: str, scanner_status: str = "ran") -> dict:
    """The scan-meta.json example in the ingest steps, placeholders filled in."""
    text = SCAN_SKILL.read_text(encoding="utf-8")
    block = next(
        b for b in re.findall(r"```json\n(.*?)```", text, re.S) if '"steps"' in b and '"run"' in b
    )
    block = block.replace("{conclusion}", conclusion).replace(
        "{ran|skipped|failed}", scanner_status
    )
    block = re.sub(r'"\{[^}"]*\}"', '"x"', block)
    block = re.sub(r":\s*N\b", ": 0", block)  # the finding_counts placeholders
    return json.loads(block)


def test_the_documented_run_record_parses_to_the_documented_coverage(tmp_path: Path) -> None:
    meta = _documented_meta("failure")
    names = [s["step"] for s in meta["steps"]]
    assert "semgrep" in names and meta["run"]["conclusion"] == "failure"
    files = {"semgrep.sarif": SARIF, "bandit.json": BANDIT}
    d = _scan(tmp_path / "bad", meta, files)
    _, bad, _, _ = _run(d, tmp_path)
    assert bad["coverage"] == "partial"
    assert any("concluded failure" in x for x in bad["scans"][0]["limitations"])
    ok = _scan(tmp_path / "ok", _documented_meta("success"), files)
    _, good, _, _ = _run(ok, tmp_path)
    assert good["coverage"] == "complete", good
    failed = _scan(tmp_path / "failed", _documented_meta("success", "failed"), files)
    _, scanner, _, _ = _run(failed, tmp_path)
    assert scanner["coverage"] == "partial"
    assert "failed" in " ".join(scanner["scans"][0]["limitations"])


def test_the_ingest_steps_tell_the_agent_to_record_the_run_and_the_scanners() -> None:
    text = SCAN_SKILL.read_text(encoding="utf-8")
    assert "gh run view" in text and "--json jobs" in text  # per-scanner job results
    assert "conclusion" in text and "`run`" in text
    assert "parse_sarif.py" in text and "--coverage-output" in text
    assert "unknown" in text  # a local file has no run record
    examples = SCAN_EXAMPLES.read_text(encoding="utf-8")
    assert '"steps"' in examples and '"run"' in examples and "planned_steps" in examples
    assert "findings may be partial" not in text  # no longer only a chat warning
