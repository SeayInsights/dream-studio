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
import re
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


def _run(
    scans: Path | str,
    tmp: Path,
    *,
    rc: int = 0,
    cwd: Path | None = None,
) -> tuple[list[dict] | None, dict | None, str]:
    """`scans` is passed to --scans-dir exactly as given; the process runs in `cwd`."""
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
        cwd=cwd or tmp,
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
    assert any(
        "recorded as ran but no zap result" in lim for lim in coverage["scans"][0]["limitations"]
    )


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


# -- result discovery: documented names, top level of the scan directory ------------------------------


def test_stale_report_in_a_subdirectory_is_ignored_and_named(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "web", {"steps": _steps()}, zap=None)
    (d / "old").mkdir()
    (d / "old" / "zap-report.json").write_text(json.dumps(ZAP_REPORT), encoding="utf-8")

    findings, coverage, _ = _run(scans, tmp_path)

    scan = coverage["scans"][0]
    assert len(coverage["scans"]) == 1
    assert scan["unread_steps"] == ["zap"]
    assert {f["rule_id"].split("-")[1] for f in findings} == {"nuc"}
    assert any(
        "old" in lim and "zap-report.json" in lim and "ignored" in lim
        for lim in scan["limitations"]
    )


@pytest.mark.parametrize(
    ("name", "content", "step"),
    [
        ("zap-config.json", json.dumps(ZAP_REPORT), "zap"),
        ("zap-report-old.json", json.dumps(ZAP_REPORT), "zap"),
        ("nuclei-notes.jsonl", json.dumps(NUCLEI_LINE) + "\n", "nuclei"),
        ("nuclei-config.json", json.dumps(NUCLEI_LINE), "nuclei"),
    ],
)
def test_a_wrongly_named_file_is_not_the_result_of_the_scanner(
    name: str, content: str, step: str, tmp_path: Path
):
    scans = tmp_path / "scans"
    d = _scan(
        scans,
        "web",
        {"steps": _steps()},
        zap=None if step == "zap" else "findings",
        nuclei=None if step == "nuclei" else "findings",
    )
    (d / name).write_text(content, encoding="utf-8")

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["unread_steps"] == [step]


@pytest.mark.parametrize(
    "report",
    [{"site": []}, {"site": [{"@name": "x", "alerts": []}]}, {"@version": "2"}, [], "zap", 5, None],
    ids=lambda r: json.dumps(r)[:30],
)
def test_a_zap_report_without_the_zap_shape_is_unread_and_never_crashes(
    report: object, tmp_path: Path
):
    scans = tmp_path / "scans"
    d = _scan(scans, "web", {"steps": _steps()})
    (d / "zap-report.json").write_text(json.dumps(report), encoding="utf-8")

    findings, coverage, _ = _run(scans, tmp_path)

    assert coverage["scans"][0]["unread_steps"] == ["zap"]
    assert {f["rule_id"].split("-")[1] for f in findings} == {"nuc"}


def test_a_ran_step_needs_a_real_tool_name():
    sys.path.insert(0, str(ETL))
    import scan_coverage

    for tool in ["", "  ", 5, ["t"], {}, None, True]:
        steps = _steps()
        steps[0]["tool"] = tool
        report = scan_coverage.assess({"steps": steps}, ALL_STEPS, set(ALL_STEPS))
        assert report["coverage"] == "unknown", tool


# -- relative and unusual --scans-dir forms -----------------------------------------------------------


def _path_forms(tmp: Path) -> list[tuple[str, str, Path]]:
    scans = tmp / "scans"
    dated = scans / "web" / "2026-10-19"
    forms = [
        ("relative", "scans", tmp),
        ("dot-in-the-scan-dir", ".", dated),
        ("relative-dated-dir", "web/2026-10-19", scans),
        ("dotdot-segments", "scans/web/../web", tmp),
        ("dotdot-out-and-back", "../../../scans", dated),
        ("trailing-slash", str(scans) + "/", tmp),
        ("absolute", str(scans), tmp),
    ]
    if sys.platform == "win32":
        forms += [
            ("trailing-backslash", str(scans) + "\\", tmp),
            ("relative-backslashes", "web\\2026-10-19", scans),
            ("case-differs", str(scans).swapcase(), tmp),
        ]
    return forms


@pytest.mark.parametrize("form", [f[0] for f in _path_forms(Path("x"))])
def test_scans_dir_given_in_any_path_form_gives_the_same_result_as_the_absolute_path(
    form: str, tmp_path: Path
):
    scans = tmp_path / "scans"
    _scan(scans, "web", {"steps": _steps()})
    baseline, base_cov, _ = _run(scans, tmp_path)

    _, arg, cwd = next(f for f in _path_forms(tmp_path) if f[0] == form)
    findings, coverage, stderr = _run(arg, tmp_path, cwd=cwd)

    assert "Traceback" not in stderr
    assert sorted(f["fingerprint"] for f in findings) == sorted(f["fingerprint"] for f in baseline)
    assert coverage["coverage"] == "complete" == base_cov["coverage"]
    assert len(coverage["scans"]) == 1
    assert coverage["scans"][0]["steps_read"] == list(ALL_STEPS)


def test_an_unexpected_failure_in_discovery_still_writes_the_sidecar(tmp_path: Path, monkeypatch):
    sys.path.insert(0, str(ETL))
    sys.path.insert(0, str(REPO_ROOT))
    import parse_dast

    scans = tmp_path / "scans"
    _scan(scans, "web", {"steps": _steps()})
    cov = tmp_path / "cov.json"

    def boom(*_a, **_k):
        raise RuntimeError("simulated discovery failure")

    monkeypatch.setattr(parse_dast.scan_coverage, "split_by_scan_dir", boom)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "parse_dast.py",
            "--client",
            "c",
            "--scans-dir",
            str(scans),
            "--coverage-output",
            str(cov),
        ],
    )
    with pytest.raises(SystemExit) as exit_info:
        parse_dast.main()

    assert exit_info.value.code == 1
    sidecar = json.loads(cov.read_text("utf-8"))
    assert sidecar["coverage"] == "unknown"
    assert "simulated discovery failure" in sidecar["scans"][0]["limitations"][0]


# -- text encodings: Windows tools do not write UTF-8 -------------------------------------------------


@pytest.mark.parametrize(
    ("label", "encode"),
    [
        ("utf8-bom", lambda t: b"\xef\xbb\xbf" + t.encode("utf-8")),
        ("utf16-le-bom", lambda t: b"\xff\xfe" + t.replace("\n", "\r\n").encode("utf-16-le")),
        ("utf16-be-no-bom", lambda t: t.encode("utf-16-be")),
    ],
)
def test_reports_in_another_encoding_are_read_and_the_encoding_is_named(
    label: str, encode, tmp_path: Path
):
    scans = tmp_path / "scans"
    d = _scan(scans, "web", {"steps": _steps()}, zap=None, nuclei=None)
    (d / "zap-report.json").write_bytes(encode(json.dumps(ZAP_REPORT)))
    (d / "nuclei-output.jsonl").write_bytes(encode(json.dumps(NUCLEI_LINE) + "\n"))

    findings, coverage, _ = _run(scans, tmp_path)

    assert {f["rule_id"].split("-")[1] for f in findings} == {"zap", "nuc"}, label
    assert coverage["coverage"] == "complete"
    limitations = coverage["scans"][0]["limitations"]
    assert any("zap-report.json" in lim for lim in limitations)
    assert any("nuclei-output.jsonl" in lim for lim in limitations)


def test_a_report_that_is_not_text_is_unread(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "web", {"steps": _steps()}, zap=None)
    (d / "zap-report.json").write_bytes(b"\xff" * 1000)

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["scans"][0]["unread_steps"] == ["zap"]
    assert any(
        "zap-report.json could not be read" in lim for lim in coverage["scans"][0]["limitations"]
    )


# -- nuclei lines must look like nuclei results -----------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        json.dumps(ZAP_REPORT) + "\n",
        '{"foo": 1}\n',
        json.dumps(NUCLEI_LINE) + '\n{"foo": 1}\n',  # one good line, one that is not a result
        '{"template-id": "x"}\n',  # no info object
        '{"info": {"name": "x"}}\n',  # no template id
        '{"template-id": "x", "info": "not an object"}\n',
    ],
    ids=["zap-json", "foo", "good-then-foreign", "no-info", "no-template-id", "info-not-object"],
)
def test_nuclei_file_with_lines_that_are_not_nuclei_results_is_unread(content: str, tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "web", {"steps": _steps()}, nuclei=None)
    (d / "nuclei-output.jsonl").write_text(content, encoding="utf-8")

    _, coverage, _ = _run(scans, tmp_path)

    scan = coverage["scans"][0]
    assert scan["unread_steps"] == ["nuclei"]
    assert any("not nuclei results" in lim for lim in scan["limitations"])


def test_nuclei_older_template_id_key_is_still_a_result(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "web", {"steps": _steps()}, nuclei=None)
    line = {"templateID": "exposed-panel", "info": {"severity": "low"}, "host": "h"}
    (d / "nuclei-output.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "complete"


# -- a file that looks like a result but is not named like one is named -------------------------------------


@pytest.mark.parametrize(
    ("name", "step"),
    [
        ("zap-config.json", "zap"),
        ("zap-report-old.json", "zap"),
        ("ZAP-Report.JSON", "zap"),
        ("nuclei-notes.jsonl", "nuclei"),
    ],
)
def test_a_wrongly_named_top_level_file_is_named_in_the_limitations(
    name: str, step: str, tmp_path: Path
):
    scans = tmp_path / "scans"
    d = _scan(
        scans,
        "web",
        {"steps": _steps()},
        zap=None if step == "zap" else "findings",
        nuclei=None if step == "nuclei" else "findings",
    )
    (d / name).write_text("{}", encoding="utf-8")

    _, coverage, _ = _run(scans, tmp_path)

    scan = coverage["scans"][0]
    assert scan["unread_steps"] == [step]
    assert any(name in lim and "was ignored" in lim for lim in scan["limitations"])
    assert not any("see the other limitations" in lim for lim in scan["limitations"])


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


def test_doc_describes_unread_exactly_as_the_code_behaves():
    """An empty nuclei-output.jsonl is a result (Nuclei found nothing), so the doc must not
    list "empty" among the things that make a ran scanner partial."""
    text = " ".join(EXAMPLES.read_text(encoding="utf-8").split())
    assert "missing, empty" not in text and "empty or malformed" not in text
    assert "missing or malformed" in text
    assert "an empty file is a result" in text


# -- one odd Nuclei line must not drop the file (issue #908) -------------------------------------


def _nuclei_file(tmp_path: Path, lines: list[object]) -> Path:
    d = _scan(
        tmp_path / "scans",
        "web",
        {"schema_version": 1, "steps": _steps()},
        zap="clean",
        nuclei="empty",
    )
    text = "".join((ln if isinstance(ln, str) else json.dumps(ln)) + "\n" for ln in lines)
    (d / "nuclei-output.jsonl").write_text(text, encoding="utf-8")
    return d


def _nuclei(name: str, **info: object) -> dict:
    return {
        "template-id": name,
        "info": {"name": name, "severity": "medium", **info},
        "host": "https://app.example.test",
    }


@pytest.mark.parametrize(
    "info",
    [
        {"classification": None},
        {"tags": None},
        {"classification": None, "tags": None},
        {"classification": "CWE-79"},
        {"classification": {"cwe-id": None}},
        {"classification": {"cwe-id": "CWE-79"}},
        {"tags": 7},
        {"tags": ["owasp-a01", 3, None]},
    ],
    ids=[
        "null-classification",
        "null-tags",
        "both-null",
        "classification-string",
        "null-cwe-list",
        "cwe-string",
        "numeric-tags",
        "mixed-tags",
    ],
)
def test_an_odd_classification_or_tags_value_does_not_cost_the_finding(tmp_path: Path, info: dict):
    d = _nuclei_file(tmp_path, [_nuclei("good-one"), _nuclei("odd-one", **info)])
    findings, coverage, stderr = _run(d, tmp_path)
    assert {f["rule_id"] for f in findings} == {"DAST-nuc-good-one", "DAST-nuc-odd-one"}
    assert "Traceback" not in stderr
    assert coverage["scans"][0]["coverage"] == "complete", coverage


def test_a_line_that_still_raises_is_named_and_the_rest_of_the_file_is_kept(tmp_path: Path):
    bad = _nuclei("bad-one")
    bad["response"] = 5  # not text: slicing it raises
    d = _nuclei_file(tmp_path, [_nuclei("first"), bad, _nuclei("last")])
    findings, coverage, _ = _run(d, tmp_path)
    assert {f["rule_id"] for f in findings} == {"DAST-nuc-first", "DAST-nuc-last"}
    scan = coverage["scans"][0]
    assert scan["coverage"] == "partial" and scan["degraded_steps"] == ["nuclei"]
    text = " ".join(scan["limitations"])
    assert "lines 2;" in text and "nuclei-output.jsonl" in text and "first error TypeError" in text


def test_many_failing_lines_are_counted_not_listed_without_bound(tmp_path: Path):
    lines = []
    for i in range(40):
        bad = _nuclei(f"bad-{i}")
        bad["response"] = 5
        lines.append(bad)
    d = _nuclei_file(tmp_path, [_nuclei("good")] + lines)
    findings, coverage, _ = _run(d, tmp_path)
    assert [f["rule_id"] for f in findings] == ["DAST-nuc-good"]
    text = " ".join(coverage["scans"][0]["limitations"])
    assert "40 line(s)" in text and "lines 2, 3, 4, 5, 6, ...;" in text and len(text) < 600


def test_undecodable_bytes_in_a_nuclei_file_make_the_scan_partial(tmp_path: Path):
    """The decode degradation reaches coverage through the Nuclei reader too."""
    d = _scan(
        tmp_path / "scans",
        "web",
        {"schema_version": 1, "steps": _steps()},
        zap="clean",
        nuclei="empty",
    )
    good = json.dumps(_nuclei("first")).encode("utf-8")
    broken = (
        json.dumps(_nuclei("second", description="caf"))
        .encode("utf-8")
        .replace(b'"caf"', b'"caf\xff"')
    )
    (d / "nuclei-output.jsonl").write_bytes(good + b"\n" + broken + b"\n")
    findings, coverage, _ = _run(d, tmp_path)
    assert {f["rule_id"] for f in findings} == {"DAST-nuc-first", "DAST-nuc-second"}
    scan = coverage["scans"][0]
    assert scan["coverage"] == "partial" and scan["degraded_steps"] == ["nuclei"]
    assert any("1 undecodable byte(s) in nuclei-output.jsonl" in x for x in scan["limitations"])


# -- the same finding from two scans keeps the weaker coverage (issue #908) ----------------------


def test_a_finding_reported_by_two_scans_takes_the_weaker_coverage_and_says_so(tmp_path: Path):
    scans = tmp_path / "scans"
    complete = _scan(scans, "web", {"schema_version": 1, "steps": _steps()})
    partial = scans / "web" / "2026-10-20"
    partial.mkdir()
    (partial / "scan-meta.json").write_text(
        json.dumps({"schema_version": 1, "steps": _steps(nuclei="skipped")}), encoding="utf-8"
    )
    (partial / "zap-report.json").write_text(json.dumps(ZAP_REPORT), encoding="utf-8")
    assert complete.is_dir()

    findings, coverage, _ = _run(scans / "web", tmp_path)

    zap = [f for f in findings if f["rule_id"] == "DAST-zap-10010"]
    assert len(zap) == 1
    assert zap[0]["coverage"] == "partial"
    text = " ".join(zap[0]["limitations"])
    assert "skipped: nuclei is not installed" in text
    assert "also reported by another scan" in text
    # the finding only the complete scan has keeps that scan's coverage
    nuc = [f for f in findings if f["rule_id"] == "DAST-nuc-exposed-panel"]
    assert [f["coverage"] for f in nuc] == ["complete"]
    assert {Path(s["scan_dir"]).name: s["coverage"] for s in coverage["scans"]} == {
        "2026-10-19": "complete",
        "2026-10-20": "partial",
    }


def test_merging_is_order_independent_and_identical_stamps_are_left_alone():
    sys.path.insert(0, str(ETL))
    sys.path.insert(0, str(REPO_ROOT))
    import parse_dast

    def f(sev: str, cov: str, *limits: str) -> dict:
        return {
            "fingerprint": "fp",
            "severity": sev,
            "coverage": cov,
            "limitations": list(limits),
        }

    for first, second in (
        (f("high", "complete"), f("low", "partial", "zap skipped: x")),
        (f("low", "partial", "zap skipped: x"), f("high", "complete")),
    ):
        (merged,) = parse_dast.deduplicate([first, second])
        assert merged["severity"] == "high" and merged["coverage"] == "partial"
        assert any("zap skipped: x" in x for x in merged["limitations"])
    same_a, same_b = f("high", "complete"), f("high", "complete")
    (kept,) = parse_dast.deduplicate([same_a, same_b])
    assert kept["limitations"] == []
    unstamped = {"fingerprint": "u", "severity": "low"}
    (only,) = parse_dast.deduplicate([unstamped, dict(unstamped)])
    assert "coverage" not in only


# -- a target that was not scanned leaves a record (issue #895 item 6) ----------------------------
#
# `dast run` skips a target whose URL does not answer ("warn and skip"), and stops the whole
# run when ZAP is not installed. Neither wrote anything, so `dast status` could not tell a
# target nobody tried from one that was tried and skipped, and a stale last scan kept
# reading CURRENT. The record is the one every other skipped step already uses: a scan
# directory holding only a scan-meta.json whose steps are `skipped` with the reason, and
# `outcome: not_scanned`. parse_dast reads it with no new code path, and the dashboard and
# `dast status` get "target X not scanned: reason".

UNREACHABLE = "target unreachable: curl returned 000"


def _not_scanned(reason: str = UNREACHABLE, **override: object) -> dict:
    meta: dict = {
        "schema_version": 1,
        "target": "web",
        "target_type": "webapp",
        "source": "local-run",
        "outcome": "not_scanned",
        "reason": reason,
        "scanners": [],
        "steps": [{"step": s, "status": "skipped", "tool": s, "reason": reason} for s in ALL_STEPS],
    }
    meta.update(override)
    return meta


def test_a_target_that_was_not_scanned_reads_partial_and_names_why(tmp_path: Path):
    scans = tmp_path / "scans"
    steps = [{"step": s, "status": "skipped", "tool": s, "reason": "skipped"} for s in ALL_STEPS]
    d = _scan(scans, "web", _not_scanned(steps=steps), zap=None, nuclei=None)
    assert [p.name for p in d.iterdir()] == ["scan-meta.json"]

    findings, coverage, _ = _run(d, tmp_path, rc=1)

    assert not findings
    scan = coverage["scans"][0]
    assert coverage["coverage"] == "partial" == scan["coverage"]
    assert scan["skipped_steps"] == ["zap", "nuclei"]
    text = " ".join(scan["limitations"])
    assert "the target was not scanned" in text and UNREACHABLE in text


def test_an_outcome_of_not_scanned_cannot_be_overruled_by_steps_that_say_ran(tmp_path: Path):
    """A record that says both is contradictory; the claim that nothing was scanned wins."""
    meta = _not_scanned(steps=_steps())
    d = _scan(tmp_path / "scans", "web", meta)
    findings, coverage, _ = _run(d, tmp_path)
    assert {f["coverage"] for f in findings} == {"partial"}
    assert "the target was not scanned" in " ".join(coverage["scans"][0]["limitations"])


def test_a_hostile_reason_is_bounded_and_printable(tmp_path: Path):
    d = _scan(
        tmp_path / "scans", "web", _not_scanned("down \x1b[31m" + "x" * 5000), zap=None, nuclei=None
    )
    _, coverage, _ = _run(d, tmp_path, rc=1)
    text = " ".join(coverage["scans"][0]["limitations"])
    assert "\x1b" not in text and len(text) < 2000


def test_a_not_scanned_record_beside_a_real_scan_is_reported_separately(tmp_path: Path):
    scans = tmp_path / "scans"
    real = _scan(scans, "web", {"schema_version": 1, "steps": _steps()})
    skipped = scans / "web" / "2026-10-20"
    skipped.mkdir()
    (skipped / "scan-meta.json").write_text(json.dumps(_not_scanned()), encoding="utf-8")
    assert real.is_dir()

    _, coverage, _ = _run(scans / "web", tmp_path)

    by_dir = {Path(s["scan_dir"]).name: s["coverage"] for s in coverage["scans"]}
    assert by_dir == {"2026-10-19": "complete", "2026-10-20": "partial"}


def _documented_not_scanned(reason: str) -> dict:
    text = EXAMPLES.read_text(encoding="utf-8")
    block = next(
        b
        for b in re.findall(r"```json\n(.*?)```", text, re.S)
        if '"not_scanned"' in b and '"steps"' in b
    )
    block = block.replace("{why}", reason)
    block = re.sub(r'"\{[^}"]*\}"', '"x"', block)
    return json.loads(block)


def test_the_documented_not_scanned_record_is_the_record_the_parser_reads(tmp_path: Path):
    meta = _documented_not_scanned(UNREACHABLE)
    assert meta["outcome"] == "not_scanned" and meta["scanners"] == []
    assert [s["step"] for s in meta["steps"]] == list(ALL_STEPS)
    d = _scan(tmp_path / "scans", "web", meta, zap=None, nuclei=None)
    _, coverage, _ = _run(d, tmp_path, rc=1)
    assert coverage["coverage"] == "partial"
    assert UNREACHABLE in " ".join(coverage["scans"][0]["limitations"])


def test_the_run_steps_record_both_ways_a_target_goes_unscanned():
    """R2 step 1 (URL does not answer: skip that target) and step 2 (ZAP missing: stop the
    run) both write the record; the ZAP stop writes one for every target in scope, so there
    is a single mechanism and `dast status` reads one place."""
    text = " ".join(EXAMPLES.read_text(encoding="utf-8").split())
    pre = text.split("### Step R2: Pre-flight Checks")[1].split("### Step R3")[0]
    assert "skip this target, and write its not-scanned record" in pre
    assert "**stop** the run, and write the not-scanned record" in pre
    assert "for every target in scope that has not been scanned" in pre
    status = text.split("## Mode: `status`")[1]
    assert "mark the target **NOT SCANNED** with its `reason`" in status
    assert "`outcome` is not `not_scanned`" in status
    assert "last scan that ran" in status
