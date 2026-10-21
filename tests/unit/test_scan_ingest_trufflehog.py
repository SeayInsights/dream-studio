"""trufflehog results are read, and the secret is never echoed.

WHY (#895 follow-up). The workflow wrote `trufflehog git ... --json > trufflehog-results.json
2>&1`: trufflehog prints one JSON object per finding (JSON Lines) on stdout and its own log on
stderr, and `2>&1` merged the two into one file that is neither a JSON document nor JSONL. No
parser could read it, so a scan with trufflehog planned always read `partial`. The format is
documented and readable honestly, so the workflow now separates the streams
(`trufflehog-results.jsonl` for results, `trufflehog.log` for the log) and parse_sarif reads
the JSONL.

The other half is the reason this needs care. A trufflehog result carries the secret itself in
`Raw` (and `RawV2`, and a partly masked `Redacted`). The old parser put `Raw[:80]` into the
finding's message, which reaches findings JSON, the CSV and the dashboard. A finding now carries
the detector name, file, line and whether trufflehog verified it, never the value. Every test
here that feeds a secret asserts it appears in no output at all: findings, sidecar, stderr, CSV,
metadata.

The secret used is a made-up string, not a credential and not token-shaped.
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ETL = REPO_ROOT / "templates" / "security" / "etl"
PARSER = ETL / "parse_sarif.py"
EXPORT = ETL / "export_dataset.py"
TEMPLATE = REPO_ROOT / "templates" / "security" / "github-actions" / "security-scan.yml.j2"
SCAN_SKILL = REPO_ROOT / "canonical" / "skills" / "security" / "modes" / "scan" / "SKILL.md"
DASHBOARD = REPO_ROOT / "canonical" / "skills" / "security" / "modes" / "dashboard" / "examples.md"
BINARY_DOC = (
    REPO_ROOT / "canonical" / "skills" / "security" / "modes" / "binary-scan" / "examples.md"
)

sys.path.insert(0, str(ETL))
import parse_sarif  # noqa: E402
import scan_coverage  # noqa: E402

SECRET = "zz-not-a-real-secret-value-0001"
SECRET_V2 = SECRET + "/second-half"
MASKED = "zz-not-a-r..."


def _git_result(file: str = "app/config.py", line: int = 12, **extra: object) -> dict:
    out = {
        "SourceMetadata": {
            "Data": {
                "Git": {
                    "commit": "0123456789abcdef",
                    "file": file,
                    "email": "dev@example.test",
                    "repository": "file://.",
                    "timestamp": "2026-10-01 10:00:00 +0000",
                    "line": line,
                }
            }
        },
        "SourceID": 1,
        "SourceType": 16,
        "SourceName": "trufflehog - git",
        "DetectorType": 2,
        "DetectorName": "AWS",
        "DecoderName": "PLAIN",
        "Verified": False,
        "Raw": SECRET,
        "RawV2": SECRET_V2,
        "Redacted": MASKED,
        "ExtraData": None,
        "StructuredData": None,
    }
    out.update(extra)
    return out


def _fs_result() -> dict:
    result = _git_result(DetectorName="PrivateKey", Verified=True)
    result["SourceMetadata"] = {"Data": {"Filesystem": {"file": "keys/id.pem", "line": 3}}}
    return result


def _github_result() -> dict:
    result = _git_result(DetectorName="Github")
    result["SourceMetadata"] = {
        "Data": {"Github": {"file": "ci/deploy.sh", "line": 40, "link": "https://example.test/x"}}
    }
    return result


LOG_LINES = [
    {"level": "info-2", "ts": "2026-10-01T10:00:00Z", "logger": "trufflehog", "msg": "starting"},
    {"level": "info-0", "ts": "2026-10-01T10:00:09Z", "logger": "trufflehog", "msg": "finished"},
]


def _jsonl(*objs: object) -> str:
    return "".join((o if isinstance(o, str) else json.dumps(o)) + "\n" for o in objs)


def _meta(**status: str) -> dict:
    return {
        "source": "github-actions",
        "planned_steps": ["semgrep", "trufflehog"],
        "run": {"run_id": "9", "status": "completed", "conclusion": "success"},
        "steps": [
            {"step": "semgrep", "status": status.get("semgrep", "ran"), "tool": "semgrep"},
            {"step": "trufflehog", "status": status.get("trufflehog", "ran"), "tool": "trufflehog"},
        ],
    }


SARIF = {
    "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
    "runs": [{"tool": {"driver": {"name": "semgrep"}}, "results": []}],
}


def _scan(tmp_path: Path, files: dict[str, str], meta: dict | None = None) -> Path:
    d = tmp_path / "scans" / "repo-a" / "2026-10-20"
    d.mkdir(parents=True)
    (d / "scan-meta.json").write_text(json.dumps(meta or _meta()), encoding="utf-8")
    (d / "semgrep-results.sarif").write_text(json.dumps(SARIF), encoding="utf-8")
    for name, text in files.items():
        (d / name).write_bytes(text.encode("utf-8"))
    return d


def _parse(scan: Path, tmp_path: Path) -> tuple[list[dict], dict, str, str, str]:
    out, cov = tmp_path / "findings.json", tmp_path / "coverage.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(PARSER),
            "--client",
            "c",
            "--scans-dir",
            str(scan),
            "--output",
            str(out),
            "--coverage-output",
            str(cov),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    findings = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    coverage = json.loads(cov.read_text(encoding="utf-8")) if cov.exists() else {}
    out_text = out.read_text(encoding="utf-8") if out.exists() else ""
    cov_text = cov.read_text(encoding="utf-8") if cov.exists() else ""
    return findings, coverage, out_text, cov_text, proc.stderr


def _no_secret(*texts: str) -> None:
    for text in texts:
        for value in (SECRET, SECRET_V2, MASKED):
            assert value not in text, "a secret value reached an output"


# -- JSON Lines results ---------------------------------------------------------------------------------------


def test_trufflehog_jsonl_is_read_into_findings_and_the_scan_is_complete(tmp_path: Path) -> None:
    scan = _scan(
        tmp_path,
        {"trufflehog-results.jsonl": _jsonl(_git_result(), _fs_result(), _github_result())},
    )
    findings, coverage, out_text, cov_text, stderr = _parse(scan, tmp_path)
    th = [f for f in findings if f["scanner"] == "trufflehog"]
    assert sorted((f["rule_id"], f["file"], f["line"]) for f in th) == [
        ("TH-AWS", "app/config.py", 12),
        ("TH-Github", "ci/deploy.sh", 40),
        ("TH-PrivateKey", "keys/id.pem", 3),
    ]
    assert {f["severity"] for f in th} == {"high"}
    assert coverage["coverage"] == "complete", coverage
    assert {f["coverage"] for f in findings} == {"complete"}
    _no_secret(out_text, cov_text, stderr)


def test_a_finding_carries_detector_file_line_and_a_redacted_marker_only(tmp_path: Path) -> None:
    scan = _scan(tmp_path, {"trufflehog-results.jsonl": _jsonl(_git_result())})
    findings, *_ = _parse(scan, tmp_path)
    (finding,) = [f for f in findings if f["scanner"] == "trufflehog"]
    assert "value redacted" in finding["message"] and "AWS" in finding["message"]
    assert "unverified" in finding["message"]
    assert json.dumps(finding).count(SECRET) == 0
    assert "dev@example.test" not in json.dumps(finding)  # not the author's address either


def test_a_verified_result_says_so_in_the_message_and_is_still_high(tmp_path: Path) -> None:
    scan = _scan(tmp_path, {"trufflehog-results.jsonl": _jsonl(_fs_result())})
    findings, *_ = _parse(scan, tmp_path)
    (finding,) = [f for f in findings if f["scanner"] == "trufflehog"]
    assert "verified by trufflehog" in finding["message"] and finding["severity"] == "high"


def test_an_empty_jsonl_is_a_clean_result_not_a_missing_one(tmp_path: Path) -> None:
    scan = _scan(tmp_path, {"trufflehog-results.jsonl": ""})
    findings, coverage, *_ = _parse(scan, tmp_path)
    assert [f for f in findings if f["scanner"] == "trufflehog"] == []
    assert coverage["scans"][0]["unread_steps"] == []
    assert coverage["coverage"] == "complete"


def test_a_missing_trufflehog_file_leaves_the_step_unread_and_partial(tmp_path: Path) -> None:
    scan = _scan(tmp_path, {})
    _, coverage, *_ = _parse(scan, tmp_path)
    assert coverage["scans"][0]["unread_steps"] == ["trufflehog"]
    assert coverage["coverage"] == "partial"


def test_a_failed_trufflehog_job_is_partial_even_with_a_readable_file(tmp_path: Path) -> None:
    scan = _scan(
        tmp_path, {"trufflehog-results.jsonl": _jsonl(_git_result())}, _meta(trufflehog="failed")
    )
    _, coverage, *_ = _parse(scan, tmp_path)
    assert coverage["coverage"] == "partial"
    assert "trufflehog" in " ".join(coverage["scans"][0]["limitations"])


def test_trufflehog_log_lines_in_the_file_are_noted_not_read_as_results(tmp_path: Path) -> None:
    scan = _scan(
        tmp_path,
        {"trufflehog-results.jsonl": _jsonl(LOG_LINES[0], _git_result(), LOG_LINES[1])},
    )
    findings, coverage, *_ = _parse(scan, tmp_path)
    assert len([f for f in findings if f["scanner"] == "trufflehog"]) == 1
    scan_report = coverage["scans"][0]
    assert any("2 trufflehog log line(s)" in x for x in scan_report["limitations"])
    assert coverage["coverage"] == "complete"  # a log line is not a lost result


def test_the_old_merged_artifact_is_read_by_name_with_its_log_lines_set_aside(
    tmp_path: Path,
) -> None:
    """`trufflehog-results.json` as the old workflow wrote it: results and log on one stream.
    Not a JSON document, so it is read as lines because its name says trufflehog."""
    scan = _scan(
        tmp_path,
        {"trufflehog-results.json": _jsonl(LOG_LINES[0], _git_result(), LOG_LINES[1])},
    )
    findings, coverage, out_text, cov_text, stderr = _parse(scan, tmp_path)
    assert len([f for f in findings if f["scanner"] == "trufflehog"]) == 1
    assert coverage["scans"][0]["unread_steps"] == []
    _no_secret(out_text, cov_text, stderr)


def test_a_line_that_is_not_a_result_is_named_by_number_and_never_echoed(tmp_path: Path) -> None:
    junk = f"this line mentions {SECRET} and is not JSON"
    other = json.dumps({"unrelated": SECRET})
    scan = _scan(
        tmp_path,
        {"trufflehog-results.jsonl": _jsonl(_git_result(), junk, other, _git_result(line=13))},
    )
    findings, coverage, out_text, cov_text, stderr = _parse(scan, tmp_path)
    assert len([f for f in findings if f["scanner"] == "trufflehog"]) == 2
    report = coverage["scans"][0]
    assert coverage["coverage"] == "partial" and report["degraded_steps"] == ["trufflehog"]
    text = " ".join(report["limitations"])
    assert "2 line(s)" in text and "lines 2, 3" in text
    _no_secret(out_text, cov_text, stderr)


def test_a_trufflehog_named_file_of_nothing_but_junk_is_read_as_degraded(tmp_path: Path) -> None:
    scan = _scan(tmp_path, {"trufflehog-results.jsonl": _jsonl("garbage", "more garbage")})
    findings, coverage, out_text, cov_text, stderr = _parse(scan, tmp_path)
    report = coverage["scans"][0]
    assert report["degraded_steps"] == ["trufflehog"] and report["unread_steps"] == []
    assert coverage["coverage"] == "partial"


def test_a_jsonl_file_that_says_nothing_about_trufflehog_and_holds_junk_is_refused(
    tmp_path: Path,
) -> None:
    scan = _scan(tmp_path, {"scan-output.jsonl": _jsonl("garbage", "more garbage")})
    _, coverage, *_ = _parse(scan, tmp_path)
    report = coverage["scans"][0]
    assert report["unread_steps"] == ["trufflehog"]
    assert any(
        "scan-output.jsonl is not the output of a scanner" in x for x in report["limitations"]
    )


def test_a_whole_document_trufflehog_list_is_still_read_and_redacted(tmp_path: Path) -> None:
    scan = _scan(tmp_path, {"trufflehog-results.json": json.dumps([_git_result()])})
    findings, coverage, out_text, cov_text, stderr = _parse(scan, tmp_path)
    assert [f["rule_id"] for f in findings if f["scanner"] == "trufflehog"] == ["TH-AWS"]
    _no_secret(out_text, cov_text, stderr)


def test_the_dict_wrapped_form_is_redacted_too() -> None:
    findings = parse_sarif.parse_trufflehog({"results": [_git_result()]}, "r")
    assert len(findings) == 1 and SECRET not in json.dumps(findings)


@pytest.mark.parametrize(
    "result",
    [
        {"DetectorName": None},
        {"DetectorName": ["x"], "Raw": SECRET},
        {"DetectorName": "X", "SourceMetadata": None, "Raw": SECRET},
        {"DetectorName": "X", "SourceMetadata": {"Data": None}, "Raw": SECRET},
        {"DetectorName": "X", "SourceMetadata": {"Data": {"Git": "oops"}}, "Raw": SECRET},
        {"DetectorName": "X", "SourceMetadata": {"Data": {"Git": {"file": 7, "line": "x"}}}},
        {"SourceMetadata": {}, "Raw": SECRET},
    ],
)
def test_a_hostile_result_still_makes_a_redacted_finding_or_a_named_line(result: dict) -> None:
    findings, bad = parse_sarif.read_trufflehog_lines(_jsonl(result), "t.jsonl")[:2]
    assert SECRET not in json.dumps(findings) and SECRET not in " ".join(bad)


def test_a_dash_less_unusual_unicode_detector_name_is_printable() -> None:
    findings = parse_sarif.parse_trufflehog([_git_result(DetectorName="Bad\x1b[31m\nName")], "r")
    assert findings[0]["rule_id"].isprintable() and findings[0]["message"].isprintable()


# -- nothing reaches the CSV either -------------------------------------------------------------------------------


def test_the_secret_never_reaches_the_dataset(tmp_path: Path) -> None:
    scan = _scan(tmp_path, {"trufflehog-results.jsonl": _jsonl(_git_result(), _fs_result())})
    findings, *_ = _parse(scan, tmp_path)
    out = tmp_path / "dataset"
    proc = subprocess.run(
        [
            sys.executable,
            str(EXPORT),
            "--client",
            "c",
            "--output-dir",
            str(out),
            "--scans-dir",
            str(scan.parents[1]),
        ],
        input=json.dumps(findings),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "DREAM_STUDIO_HOME": str(tmp_path / "home")},
    )
    assert proc.returncode == 0, proc.stderr
    everything = proc.stdout + proc.stderr
    for path in out.rglob("*"):
        if path.is_file():
            everything += path.read_text(encoding="utf-8", errors="replace")
    _no_secret(everything)
    with open(out / "findings.csv", newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["scanner"] == "trufflehog"]
    assert len(rows) == 2 and all("value redacted" in r["message"] for r in rows)


# -- the workflow template ----------------------------------------------------------------------------------------


def _trufflehog_job() -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    start = text.index("  trufflehog:\n")
    end = text.index("{% endif %}", start)
    return text[start:end]


def test_the_workflow_separates_trufflehogs_results_from_its_log() -> None:
    job = _trufflehog_job()
    assert "2>&1" not in job
    assert re.search(r"> trufflehog-results\.jsonl 2> trufflehog\.log", job), job
    assert "path: trufflehog-results.jsonl" in job
    assert "trufflehog-results.json\n" not in job


def test_the_workflow_still_renders_to_valid_yaml_with_trufflehog() -> None:
    jinja2 = pytest.importorskip("jinja2")
    yaml = pytest.importorskip("yaml")
    client = {
        "name": "Acme",
        "scan": {
            "schedule": "weekly",
            "semgrep_rulesets": ["p/ci"],
            "extra_scanners": ["trufflehog"],
        },
    }
    rendered = jinja2.Template(TEMPLATE.read_text(encoding="utf-8")).render(client=client)
    jobs = yaml.safe_load(rendered)["jobs"]
    assert "trufflehog" in jobs
    step_text = json.dumps(jobs["trufflehog"])
    assert "trufflehog-results.jsonl" in step_text and "2>&1" not in step_text


def test_the_ingest_steps_name_the_jsonl_file_and_the_redaction() -> None:
    flat = " ".join(SCAN_SKILL.read_text(encoding="utf-8").split())
    assert "`trufflehog-results.jsonl`" in flat
    assert "JSON Lines" in flat and "value redacted" in flat
    assert "never the secret" in flat


# -- parse_sarif reads one scan directory --------------------------------------------------------------------------


def test_the_dashboard_doc_says_parse_sarif_reads_one_scan_directory() -> None:
    flat = " ".join(DASHBOARD.read_text(encoding="utf-8").split())
    assert "Reads all SARIF/JSON files from `scans/{client}/`" not in flat
    assert "Reads the result files directly in `--scans-dir`" in flat
    assert "one scan directory per run" in flat
    assert "does not walk the client tree" in flat


def test_pointing_parse_sarif_at_the_client_tree_says_what_to_do(tmp_path: Path) -> None:
    tree = tmp_path / "scans"
    (tree / "repo-a" / "2026-10-20").mkdir(parents=True)
    proc = subprocess.run(
        [sys.executable, str(PARSER), "--client", "c", "--scans-dir", str(tree)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 1
    assert "pass --scans-dir the scan directory" in proc.stderr
    assert "does not walk the client tree" in proc.stderr


# -- UTF-16 without a BOM (pinned) --------------------------------------------------------------------------------


def test_bomless_utf16_is_recognised_only_when_mostly_ascii() -> None:
    mostly_ascii = ("cafe " * 20 + "日本").encode("utf-16-le")  # 2 CJK units in 102
    got = scan_coverage.decode_text(mostly_ascii, "x.txt")
    assert got.text.startswith("cafe ") and any("no BOM" in n for n in got.notes)


@pytest.mark.parametrize("name", ["utf-16-le", "utf-16-be"])
def test_bomless_utf16_of_non_latin_text_is_refused_not_misread(name: str) -> None:
    """CJK text has no NUL bytes to give it away: it is not recognised, and reads unread."""
    text = "日本語のテキスト" * 5
    with pytest.raises(ValueError):
        scan_coverage.decode_text(text.encode(name), "x.txt")


def test_the_doc_says_bomless_utf16_needs_mostly_ascii_text() -> None:
    flat = " ".join(BINARY_DOC.read_text(encoding="utf-8").split())
    assert "UTF-16 without a BOM is recognised only when most of the text is ASCII" in flat
    assert "otherwise the file is unread and the step `partial`" in flat
