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


def test_a_local_scan_without_a_run_object_is_judged_by_its_steps_alone() -> None:
    """binary-scan and dast run locally and record no workflow run."""
    for source in ("local-analysis", "local-run", None):
        meta = _meta()
        del meta["run"]
        if source is None:
            del meta["source"]
        else:
            meta["source"] = source
        report = scan_coverage.assess(meta, ("semgrep", "bandit"), {"semgrep", "bandit"})
        assert report["coverage"] == "complete", source


@pytest.mark.parametrize("source", ["github-actions", "GitHub-Actions", " github-actions "])
def test_a_github_actions_scan_with_no_run_record_is_unknown_never_complete(source: str) -> None:
    """A github-actions scan has a workflow run by definition; steps that say `ran` with no
    run recorded cannot show the run finished."""
    meta = _meta(source=source)
    del meta["run"]
    report = scan_coverage.assess(meta, ("semgrep", "bandit"), {"semgrep", "bandit"})
    assert report["coverage"] == "unknown"
    assert any("workflow run is not recorded" in x for x in report["limitations"])


def test_parse_sarif_reads_a_github_actions_scan_without_a_run_as_unknown(tmp_path: Path) -> None:
    meta = _meta()
    del meta["run"]
    d = _scan(tmp_path / "scans", meta)
    findings, coverage, _, _ = _run(d, tmp_path)
    assert findings and {f["coverage"] for f in findings} == {"unknown"}
    assert coverage["coverage"] == "unknown"


# -- contradictory records never read complete ------------------------------------------------------


@pytest.mark.parametrize("status", ["in_progress", "queued", "requested", "waiting", "pending"])
def test_a_conclusion_on_a_run_that_is_not_completed_is_unknown(status: str) -> None:
    meta = _meta("success")
    meta["run"]["status"] = status
    report = scan_coverage.assess(meta, ("semgrep", "bandit"), {"semgrep", "bandit"})
    assert report["coverage"] == "unknown"
    assert any("not completed" in x for x in report["limitations"])


def test_a_run_status_of_completed_in_any_case_is_fine() -> None:
    meta = _meta("success")
    meta["run"]["status"] = " Completed "
    assert (
        scan_coverage.assess(meta, ("semgrep", "bandit"), {"semgrep", "bandit"})["coverage"]
        == "complete"
    )


def test_a_failed_conclusion_on_an_unfinished_run_is_still_partial() -> None:
    meta = _meta("failure")
    meta["run"]["status"] = "in_progress"
    assert (
        scan_coverage.assess(meta, ("semgrep", "bandit"), {"semgrep", "bandit"})["coverage"]
        == "partial"
    )


@pytest.mark.parametrize(
    "conclusion, expected",
    [
        ("Success", "complete"),
        (" SUCCESS ", "complete"),
        ("FAILURE", "partial"),
        ("Cancelled", "partial"),
    ],
)
def test_the_conclusion_is_normalised(conclusion: str, expected: str) -> None:
    report = scan_coverage.assess(_meta(conclusion), ("semgrep", "bandit"), {"semgrep", "bandit"})
    assert report["coverage"] == expected


@pytest.mark.parametrize("outcome", ["Not_Scanned", "NOT_SCANNED", " not_scanned "])
def test_an_outcome_in_any_case_is_read_as_not_scanned(outcome: str) -> None:
    skipped = [{"step": s, "status": "skipped", "tool": s, "reason": "down"} for s in ("a", "b")]
    meta = {"outcome": outcome, "reason": "target down", "steps": skipped}
    report = scan_coverage.assess(meta, ("a", "b"), set())
    assert report["coverage"] == "partial"
    assert any("the target was not scanned: target down" in x for x in report["limitations"])


@pytest.mark.parametrize("outcome", ["not_scanned", "Not_Scanned"])
def test_not_scanned_with_steps_that_ran_contradicts_itself_and_reads_unknown(
    outcome: str,
) -> None:
    meta = {
        "outcome": outcome,
        "reason": "x",
        "steps": [{"step": "a", "status": "ran", "tool": "a"}],
    }
    report = scan_coverage.assess(meta, ("a",), {"a"})
    assert report["coverage"] == "unknown"
    assert any("contradicts itself" in x and "a" in x for x in report["limitations"])


# -- an empty SARIF is not a completed scan --------------------------------------------------------


@pytest.mark.parametrize(
    "sarif, message",
    [
        ({"$schema": SARIF["$schema"], "runs": []}, "no runs in the SARIF"),
        ({"$schema": SARIF["$schema"]}, "no runs in the SARIF"),
        ({"$schema": SARIF["$schema"], "runs": "none"}, "no runs in the SARIF"),
        (
            {"$schema": SARIF["$schema"], "runs": [{"tool": {"driver": {"name": "semgrep"}}}]},
            "no results list in any run",
        ),
    ],
    ids=["empty-runs", "schema-only", "runs-not-a-list", "run-without-results"],
)
def test_a_sarif_with_no_run_or_no_results_list_is_not_a_complete_semgrep_scan(
    tmp_path: Path, sarif: dict, message: str
) -> None:
    d = _scan(tmp_path / "scans", _meta("success"), {"semgrep.sarif": sarif, "bandit.json": BANDIT})
    findings, coverage, _, _ = _run(d, tmp_path)
    scan = coverage["scans"][0]
    assert scan["coverage"] != "complete", scan
    assert any(message in x for x in scan["limitations"]), scan["limitations"]
    assert {f["coverage"] for f in findings} == {scan["coverage"]}


def test_a_real_run_with_zero_results_is_still_complete(tmp_path: Path) -> None:
    clean = {"$schema": SARIF["$schema"], "runs": [{"tool": {"driver": {}}, "results": []}]}
    d = _scan(tmp_path / "scans", _meta("success"), {"semgrep.sarif": clean, "bandit.json": BANDIT})
    _, coverage, _, _ = _run(d, tmp_path)
    assert coverage["coverage"] == "complete"


# -- a corrupt file for a scanner that has another result ---------------------------------------------


def test_a_corrupt_second_file_for_a_scanner_that_was_read_makes_it_partial(tmp_path: Path) -> None:
    d = _scan(
        tmp_path / "scans",
        _meta("success"),
        {"semgrep.sarif": SARIF, "semgrep-extra.sarif": "{ not json", "bandit.json": BANDIT},
    )
    findings, coverage, _, _ = _run(d, tmp_path)
    scan = coverage["scans"][0]
    assert scan["coverage"] == "partial" and scan["degraded_steps"] == ["semgrep"]
    text = " ".join(scan["limitations"])
    assert "semgrep-extra.sarif could not be read" in text and "semgrep" in text
    assert {f["coverage"] for f in findings} == {"partial"}


def test_a_corrupt_pip_audit_file_degrades_pip_audit_by_its_name(tmp_path: Path) -> None:
    meta = _meta(
        "success", steps=_steps() + [{"step": "pip-audit", "status": "ran", "tool": "pip"}]
    )
    meta["planned_steps"] = ["semgrep", "bandit", "pip-audit"]
    audit = {"dependencies": []}
    d = _scan(
        tmp_path / "scans",
        meta,
        {
            "semgrep.sarif": SARIF,
            "bandit.json": BANDIT,
            "pip-audit-results.json": audit,
            "pipaudit-old.json": "{ not json",
        },
    )
    _, coverage, _, _ = _run(d, tmp_path)
    scan = coverage["scans"][0]
    assert scan["degraded_steps"] == ["pip-audit"] and scan["coverage"] == "partial"


def test_a_stray_unreadable_file_that_names_no_scanner_is_a_limitation_only(tmp_path: Path) -> None:
    d = _scan(
        tmp_path / "scans",
        _meta("success"),
        {"semgrep.sarif": SARIF, "bandit.json": BANDIT, "notes.json": "{ not json"},
    )
    findings, coverage, _, _ = _run(d, tmp_path)
    scan = coverage["scans"][0]
    assert scan["coverage"] == "complete"
    assert any("notes.json could not be read" in x for x in scan["limitations"])
    assert {f["coverage"] for f in findings} == {"complete"}


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
    flat = " ".join(text.split())
    assert "with `source` `github-actions` and no `run` it reads `unknown`" in flat
    assert "Write `run.status` as `completed`" in flat
    assert '"no runs in the SARIF"' in flat


def test_scan_status_knows_a_not_scanned_directory_and_the_other_modes_directories():
    """`scan status` lists what is under scans/{client}/, where dast and binary-scan also write.
    A fresh `{date}-not-scanned` directory must never read as the latest scan (CURRENT), and a
    dast or binary target is not a repo."""
    text = " ".join(SCAN_SKILL.read_text(encoding="utf-8").split())
    status = text.split("### Mode: `status`")[1]
    inventory = status.split("#### Step T2")[1].split("#### Step T3")[0]
    assert (
        "Skip a directory whose `scan-meta.json` has `target_type` `webapp` or `binary`"
        in inventory
    )
    assert "never the most recent scan" in inventory
    assert "`outcome` `not_scanned`" in inventory and "{date}-not-scanned" in inventory
    assert "NOT SCANNED" in inventory and "last scan that ran" in inventory
    # and the example row shows it
    assert "NOT SCANNED" in status.split("#### Step T4")[1]


def test_the_profile_schema_lists_the_scanners_the_workflow_runs() -> None:
    """docs/client-profile-schema.md listed trivy, codeql and zap, none of which the workflow
    template runs; the template's own `extra_scanners` conditions are the source of truth."""
    template = (ETL.parent / "github-actions" / "security-scan.yml.j2").read_text(encoding="utf-8")
    runs = sorted(set(re.findall(r"'([a-z-]+)' in client\.scan\.extra_scanners", template)))
    assert runs == ["bandit", "cyclonedx", "npm-audit", "pip-audit", "trufflehog"]
    schema = (REPO_ROOT / "docs" / "client-profile-schema.md").read_text(encoding="utf-8")
    line = next(ln for ln in schema.splitlines() if "extra_scanners:" in ln)
    listed = sorted(re.findall(r'"([a-z-]+)"', line))
    assert listed == runs, line
    assert not {"trivy", "codeql", "zap"} & set(listed)


# -- the planned steps of one scan ------------------------------------------------------------------------


def test_semgrep_is_always_planned_and_first_whatever_the_meta_lists() -> None:
    """semgrep is the one scanner the workflow always runs: a meta that lists only others, or
    nothing, still plans it, so its absence from the record cannot read complete."""
    assert parse_sarif.planned_steps(None) == ("semgrep",)
    assert parse_sarif.planned_steps({}) == ("semgrep",)
    assert parse_sarif.planned_steps({"planned_steps": ["bandit"]}) == ("semgrep", "bandit")
    assert parse_sarif.planned_steps({"steps": [{"step": "trufflehog"}]}) == (
        "semgrep",
        "trufflehog",
    )
    assert parse_sarif.planned_steps({"planned_steps": ["bandit", "semgrep", "bandit"]}) == (
        "semgrep",
        "bandit",
    )


def test_a_meta_that_plans_only_bandit_still_needs_semgrep_to_have_been_recorded() -> None:
    meta = {
        "source": "github-actions",
        "run": {"status": "completed", "conclusion": "success"},
        "planned_steps": ["bandit"],
        "steps": [{"step": "bandit", "status": "ran", "tool": "bandit"}],
    }
    planned = parse_sarif.planned_steps(meta)
    report = scan_coverage.assess(meta, planned, {"bandit"})
    assert report["coverage"] != "complete"
    assert any("semgrep: no record of whether it ran" in x for x in report["limitations"])


def test_planned_steps_survives_hostile_shapes() -> None:
    for meta in (
        {"planned_steps": "bandit"},
        {"planned_steps": [1, None, {"step": 3}, ["x"]]},
        {"steps": "ran"},
        {"steps": [None, 3, {"step": None}, {"step": ["a"]}]},
    ):
        assert parse_sarif.planned_steps(meta) == ("semgrep",), meta
