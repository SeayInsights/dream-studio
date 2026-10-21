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

The rule these tests hold: `complete` needs BOTH the run record saying every planned step
ran AND the parser having actually read and parsed a result for each of them. A step
recorded as ran whose output is missing, empty, unparseable or of a kind the parser does
not read is `partial` and says why; anything the record cannot establish is `unknown`.
Nothing read out of scan-meta.json may crash the parser or cost a finding.

Each CLI test runs the real script as a subprocess against a scan directory built in a
temp directory, so file discovery, the stderr summary and the exit code are all exercised.
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

#: The result file each step leaves in the scan directory, as examples.md tells the agent
#: to write it (A4-A7), and its content.
OUTPUTS = {
    "checksec": ("checksec.json", {"app.exe": {"nx": "no", "pie": "yes"}}),
    "yara": (
        "yara-matches.json",
        {
            "matches": [
                {
                    "rule": "HardcodedPassword",
                    "meta": {"severity": "high"},
                    "strings": [{"data": "password=admin123"}],
                }
            ]
        },
    ),
    "strings": ("strings-findings.txt", "password=abc123\nhttps://internal.example/x\n"),
    "header_analysis": (
        "header-analysis.json",
        {"format": "pe", "checks": {"signed": False, "debug_symbols_stripped": True}},
    ),
}


def _steps(**status: str) -> list[dict]:
    """Run record for the four steps; `status` overrides one step's status by name."""
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
    outputs: tuple[str, ...] = ALL_STEPS,
    date: str = "2026-10-19",
) -> Path:
    """A dated scan directory with the result files for `outputs` and scan-meta.json.

    `meta` is written as JSON unless it is None (no file) or a str (written verbatim).
    """
    d = root / target / date
    d.mkdir(parents=True)
    for step in outputs:
        name, content = OUTPUTS[step]
        text = content if isinstance(content, str) else json.dumps(content)
        (d / name).write_text(text, encoding="utf-8")
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
    """Run parse_binary.py; (findings, coverage sidecar, stderr). Absent outputs are None.

    `scans` is passed to --scans-dir exactly as given (a str may be relative, `.`, have a
    trailing separator or `..` segments); the process runs in `cwd` (default `tmp`).
    """
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


# -- the acceptance cases -----------------------------------------------------------------


def test_full_tooling_scan_with_every_result_read_is_complete(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "app", {"schema_version": 1, "steps": _steps()})

    findings, coverage, _ = _run(scans, tmp_path)

    # every step's result was parsed into findings, header analysis included
    assert {f["scanner"] for f in findings} == set(ALL_STEPS)
    assert {f["coverage"] for f in findings} == {"complete"}
    assert coverage["coverage"] == "complete"
    scan = coverage["scans"][0]
    assert scan["skipped_steps"] == [] and scan["unread_steps"] == []
    assert scan["steps_read"] == list(ALL_STEPS)
    assert scan["limitations"] == []


def test_scan_without_a_tool_is_partial_and_names_the_skipped_step(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(
        scans,
        "app",
        {"schema_version": 1, "steps": _steps(header_analysis="skipped")},
        outputs=("checksec", "yara", "strings"),
    )

    findings, coverage, stderr = _run(scans, tmp_path)

    assert findings
    for f in findings:
        assert f["coverage"] == "partial"
        assert any("header_analysis" in lim and "not installed" in lim for lim in f["limitations"])
    scan = coverage["scans"][0]
    assert coverage["coverage"] == "partial"
    assert scan["skipped_steps"] == ["header_analysis"]
    assert any("not installed" in lim for lim in scan["limitations"])
    assert "coverage partial" in stderr and "header_analysis" in stderr


def test_old_scan_meta_with_no_run_record_is_unknown_never_complete(tmp_path: Path):
    scans = tmp_path / "scans"
    # Exactly what binary-scan wrote before the run record existed, with every result file.
    _scan(
        scans,
        "app",
        {
            "schema_version": 1,
            "target_type": "binary",
            "scanners": ["checksec", "yara", "strings"],
            "ingested_at": "2026-10-19T00:00:00Z",
        },
    )

    findings, coverage, _ = _run(scans, tmp_path)

    assert findings
    assert {f["coverage"] for f in findings} == {"unknown"}
    assert coverage["coverage"] == "unknown"
    assert any("no run record" in lim for lim in findings[0]["limitations"])


def test_missing_scan_meta_is_unknown(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "app", None)

    findings, coverage, _ = _run(scans, tmp_path)

    assert {f["coverage"] for f in findings} == {"unknown"}
    assert coverage["coverage"] == "unknown"


# -- defect A: `ran` in the record is not the same as "the parser read it" ----------------------


def test_step_recorded_ran_but_its_result_file_is_absent_is_partial(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "app", {"steps": _steps()}, outputs=("yara", "strings", "header_analysis"))

    findings, coverage, _ = _run(scans, tmp_path)

    assert findings
    assert {f["coverage"] for f in findings} == {"partial"}
    scan = coverage["scans"][0]
    assert scan["unread_steps"] == ["checksec"]
    assert scan["skipped_steps"] == []
    assert any(
        "checksec" in lim and "recorded as ran but no checksec result" in lim
        for lim in scan["limitations"]
    )


def test_empty_result_file_the_parser_cannot_parse_is_unread_and_partial(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    (d / "checksec.json").write_text("", encoding="utf-8")

    findings, coverage, stderr = _run(scans, tmp_path)

    assert "Failed to parse checksec.json" in stderr
    assert coverage["scans"][0]["unread_steps"] == ["checksec"]
    assert {f["coverage"] for f in findings} == {"partial"}


def test_result_of_a_kind_the_parser_does_not_read_is_unread_and_partial(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    (d / "checksec.json").write_text(
        json.dumps({"error": "checksec: not an ELF"}), encoding="utf-8"
    )

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["unread_steps"] == ["checksec"]


def test_strings_written_as_the_doc_says_are_read(tmp_path: Path):
    """A6 writes strings-findings.txt; the parser used to read only .json, so never read it."""
    scans = tmp_path / "scans"
    _scan(scans, "app", {"steps": _steps()})

    findings, coverage, _ = _run(scans, tmp_path)

    strings = [f for f in findings if f["scanner"] == "strings"]
    assert any("Hardcoded credential pattern" in f["message"] for f in strings)
    assert "strings" in coverage["scans"][0]["steps_read"]


def test_strings_with_no_matches_is_an_empty_file_and_still_read(tmp_path: Path):
    """grep finding nothing leaves an empty strings-findings.txt: ran, read, no findings."""
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    (d / "strings-findings.txt").write_text("", encoding="utf-8")

    findings, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "complete"
    assert not [f for f in findings if f["scanner"] == "strings"]


def test_strings_in_a_kind_the_parser_does_not_read_is_unread(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()}, outputs=("checksec", "yara", "header_analysis"))
    (d / "strings-findings.csv").write_text("value\npassword=x\n", encoding="utf-8")

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["unread_steps"] == ["strings"]


def test_a_clean_yara_result_is_read(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    (d / "yara-matches.json").write_text("[]", encoding="utf-8")

    findings, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "complete"
    assert not [f for f in findings if f["scanner"] == "yara"]


def test_header_analysis_is_parsed_into_findings_and_unread_when_malformed(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})

    findings, _, _ = _run(scans, tmp_path)
    headers = [f for f in findings if f["scanner"] == "header_analysis"]
    assert {f["rule_id"] for f in headers} == {
        "BIN-hdr-signed"
    }  # signed=False fails; the True one does not

    (d / "header-analysis.json").write_text(json.dumps({"format": "pe"}), encoding="utf-8")
    _, coverage, _ = _run(scans, tmp_path)
    assert coverage["scans"][0]["unread_steps"] == ["header_analysis"]


def test_ran_without_a_tool_is_not_a_usable_record(tmp_path: Path):
    scans = tmp_path / "scans"
    steps = _steps()
    del steps[0]["tool"]
    _scan(scans, "app", {"steps": steps})

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "unknown"
    assert any("without naming the tool" in lim for lim in coverage["scans"][0]["limitations"])


def test_a_step_recorded_twice_is_ambiguous_and_unknown(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(
        scans, "app", {"steps": [*_steps(), {"step": "yara", "status": "skipped", "tool": "yara"}]}
    )

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "unknown"
    assert any("yara: recorded 2 times" in lim for lim in coverage["scans"][0]["limitations"])


# -- defect B: nothing read out of scan-meta.json may crash the parser or cost a finding ---------

HUGE = "x" * 200_000

MALFORMED_STEPS = [
    None,
    "ran",
    5,
    True,
    {},
    {"step": "checksec"},
    [],
    [None],
    [1, "x", 2.5, True],
    [[]],
    [[["nested"]]],
    [{"step": ["x"], "status": "ran"}],  # the verifier's crasher: unhashable step name
    [{"step": {"a": 1}, "status": "ran"}, *_steps()[1:]],
    [{"step": None, "status": "ran"}],
    [{"step": 7, "status": "ran", "tool": "t"}],
    [{"step": "checksec", "status": ["ran"], "tool": {"x": 1}}],
    [{"step": "checksec", "status": {"a": [1]}, "tool": ["t"]}],
    [{"step": "checksec", "status": "skipped", "tool": HUGE, "reason": HUGE}],
    [{"step": "checksec", "status": "ran", "tool": HUGE}],
    [{"step": "checksec", "status": "failed", "reason": {"deep": [[[{"k": HUGE}]]]}}],
    [{"step": HUGE, "status": "ran", "tool": "t"}],
    [{"step": "checksec", "status": "ran", "tool": ""}],
    [{"step": "checksec", "status": "RAN", "tool": "t"}],
]


@pytest.mark.parametrize("steps", MALFORMED_STEPS, ids=lambda s: repr(s)[:40])
def test_assess_never_raises_and_never_says_complete_for_a_malformed_record(steps):
    report = scan_coverage.assess({"steps": steps}, ALL_STEPS, set(ALL_STEPS))

    assert report["coverage"] in {"partial", "unknown"}
    assert all(len(lim) < 1000 for lim in report["limitations"])


@pytest.mark.parametrize("steps", MALFORMED_STEPS, ids=lambda s: repr(s)[:40])
def test_malformed_run_record_loses_no_findings(steps, tmp_path: Path):
    healthy = tmp_path / "healthy"
    healthy.mkdir()
    _scan(healthy / "scans", "app", {"steps": _steps()})
    expected, _, _ = _run(healthy / "scans", healthy)

    scans = tmp_path / "scans"
    _scan(scans, "app", {"steps": steps})
    findings, coverage, _ = _run(scans, tmp_path)

    assert sorted(f["fingerprint"] for f in findings) == sorted(f["fingerprint"] for f in expected)
    assert coverage["coverage"] in {"partial", "unknown"}
    assert coverage["scans"], "the scan must still be reported"


@pytest.mark.parametrize(
    "raw_meta",
    [
        "[]",
        "5",
        '"steps"',
        "null",
        "not json at all",
        "{",
        '{"steps": ' + "[" * 500 + "]" * 500 + "}",
    ],
)
def test_malformed_scan_meta_file_loses_no_findings_and_reads_unknown(raw_meta, tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "app", raw_meta)

    findings, coverage, _ = _run(scans, tmp_path)

    assert {f["scanner"] for f in findings} == set(ALL_STEPS)
    assert {f["coverage"] for f in findings} == {"unknown"}
    assert coverage["coverage"] == "unknown"


def test_load_meta_rejects_anything_but_a_json_object(tmp_path: Path):
    for text, expected in (
        ("[]", None),
        ("5", None),
        ("null", None),
        ("{", None),
        ('{"a": 1}', {"a": 1}),
    ):
        p = tmp_path / "scan-meta.json"
        p.write_text(text, encoding="utf-8")
        assert scan_coverage.load_meta(p) == expected
    assert scan_coverage.load_meta(None) is None
    assert scan_coverage.load_meta(tmp_path / "nope.json") is None


# -- defect C: the sidecar is written before any non-zero exit ---------------------------------


def test_every_step_skipped_and_no_result_files_still_writes_the_sidecar(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(
        scans,
        "app",
        {
            "steps": _steps(
                checksec="skipped", yara="skipped", strings="skipped", header_analysis="skipped"
            )
        },
        outputs=(),
    )

    findings, coverage, stderr = _run(scans, tmp_path, rc=1)

    assert findings is None  # still exits 1 with no findings file
    assert "No checksec/yara/strings" in stderr
    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["skipped_steps"] == list(ALL_STEPS)


def test_empty_scan_directory_writes_an_unknown_sidecar(tmp_path: Path):
    scans = tmp_path / "scans"
    scans.mkdir()

    _, coverage, _ = _run(scans, tmp_path, rc=1)

    assert coverage["coverage"] == "unknown"
    assert coverage["scans"][0]["scan_dir"] == str(scans)


def test_missing_scans_directory_writes_an_unknown_sidecar(tmp_path: Path):
    _, coverage, stderr = _run(tmp_path / "does-not-exist", tmp_path, rc=1)

    assert "scans directory not found" in stderr
    assert coverage["coverage"] == "unknown"
    assert any("not found" in lim for lim in coverage["scans"][0]["limitations"])


def test_a_scan_directory_with_no_result_files_is_reported_beside_ones_that_have_them(
    tmp_path: Path,
):
    scans = tmp_path / "scans"
    _scan(scans, "alpha", {"steps": _steps()})
    _scan(scans, "beta", {"steps": _steps(checksec="skipped")}, outputs=())

    findings, coverage, _ = _run(scans, tmp_path)

    by_dir = {Path(s["scan_dir"]).parent.name: s["coverage"] for s in coverage["scans"]}
    assert by_dir == {"alpha": "complete", "beta": "partial"}
    assert coverage["coverage"] == "partial"
    assert {f["target_name"] for f in findings} == {"alpha"}


# -- the rest -------------------------------------------------------------------------------


def test_a_partial_scan_with_no_findings_is_still_reported_partial(tmp_path: Path):
    """The dangerous case: nothing found, and part of the scan never ran."""
    scans = tmp_path / "scans"
    d = _scan(
        scans,
        "app",
        {"steps": _steps(checksec="skipped", header_analysis="skipped")},
        outputs=(),
    )
    (d / "checksec.json").write_text(json.dumps({"app.exe": {"nx": "yes"}}), encoding="utf-8")

    findings, coverage, _ = _run(scans, tmp_path)

    assert findings == []
    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["skipped_steps"] == ["checksec", "header_analysis"]


def test_failed_step_is_partial_too(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "app", {"steps": _steps(yara="failed")})

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["skipped_steps"] == ["yara"]


def test_each_scan_directory_is_assessed_once_not_once_per_file(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "alpha", {"steps": _steps()})
    d = _scan(
        scans,
        "beta",
        {"steps": _steps(header_analysis="skipped")},
        outputs=("checksec", "yara", "strings"),
    )
    sub = d / "raw"
    sub.mkdir()
    (sub / "yara-extra.json").write_text(json.dumps([]), encoding="utf-8")

    findings, coverage, _ = _run(scans, tmp_path)

    assert len(coverage["scans"]) == 2  # 8 result files, 2 scan directories
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


# -- find_meta never climbs out of the scans directory --------------------------------------------


def test_find_meta_does_not_climb_above_its_stop_directory(tmp_path: Path):
    (tmp_path / "scan-meta.json").write_text("{}", encoding="utf-8")  # above the scans dir
    scans = tmp_path / "scans"
    inner = scans / "app" / "2026-10-19"
    inner.mkdir(parents=True)
    result = inner / "checksec.json"
    result.write_text("{}", encoding="utf-8")

    assert scan_coverage.find_meta(result, scans) is None

    (inner / "scan-meta.json").write_text("{}", encoding="utf-8")
    assert scan_coverage.find_meta(result, scans) == inner / "scan-meta.json"


def test_a_scan_meta_above_the_scans_dir_does_not_vouch_for_the_scan(tmp_path: Path):
    (tmp_path / "scan-meta.json").write_text(json.dumps({"steps": _steps()}), encoding="utf-8")
    scans = tmp_path / "scans"
    _scan(scans, "app", None)

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "unknown"


# -- the run-record rules themselves ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("meta", "read", "expected"),
    [
        (None, ALL_STEPS, "unknown"),
        ({}, ALL_STEPS, "unknown"),
        ({"steps": "not-a-list"}, ALL_STEPS, "unknown"),
        ({"steps": []}, ALL_STEPS, "unknown"),
        ({"steps": _steps()[:-1]}, ALL_STEPS, "unknown"),
        (
            {"steps": [*_steps()[:-1], {"step": "header_analysis", "status": "maybe"}]},
            ALL_STEPS,
            "unknown",
        ),
        ({"steps": [*_steps()[:-1], "garbage"]}, ALL_STEPS, "unknown"),
        ({"steps": _steps()}, ALL_STEPS, "complete"),
        ({"steps": _steps()}, ALL_STEPS[:-1], "partial"),
        ({"steps": _steps()}, (), "partial"),
        ({"steps": _steps(strings="skipped")}, ALL_STEPS, "partial"),
        # skipped outranks unrecorded: it is the more specific, known fact
        ({"steps": [*_steps(strings="skipped")[:-1]]}, ALL_STEPS, "partial"),
        # an unread step outranks an unusable record for the same reason
        ({"steps": _steps()[:-1]}, ("yara", "strings"), "partial"),
    ],
)
def test_assess_rules(meta, read, expected):
    assert scan_coverage.assess(meta, ALL_STEPS, set(read))["coverage"] == expected


def test_overall_partial_beats_unknown_beats_complete():
    c, p, u = ({"coverage": v} for v in ("complete", "partial", "unknown"))
    assert scan_coverage.overall([c, c]) == "complete"
    assert scan_coverage.overall([c, u]) == "unknown"
    assert scan_coverage.overall([c, u, p]) == "partial"
    assert scan_coverage.overall([]) == "unknown"


# -- truncation: a cap on what is parsed is a limitation, never silent ---------------------------------


def _write_strings(d: Path, lines: list[str]) -> None:
    (d / "strings-findings.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _strings_findings(findings: list[dict]) -> list[dict]:
    return [f for f in findings if f["scanner"] == "strings"]


@pytest.mark.parametrize(
    ("lines", "total"),
    [
        ([f"https://host{i}.example/x" for i in range(500)], 500),
        (["password=same"] * 200_000, 200_000),
        ([f"https://host{i}.example/x" for i in range(51)], 51),
    ],
    ids=["500-distinct-urls", "200k-duplicate-lines", "just-over-the-cap"],
)
def test_strings_over_the_cap_is_partial_and_says_how_much_was_kept(
    lines: list[str], total: int, tmp_path: Path
):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    _write_strings(d, lines)

    findings, coverage, _ = _run(scans, tmp_path)

    assert len(_strings_findings(findings)) == 50
    scan = coverage["scans"][0]
    assert coverage["coverage"] == "partial"
    assert scan["degraded_steps"] == ["strings"]
    expected = f"first 50 of {total}"
    assert any(expected in lim for lim in scan["limitations"]), scan["limitations"]
    # the same words reach every finding, not just the sidecar
    assert {f["coverage"] for f in findings} == {"partial"}
    assert all(any(expected in lim for lim in f["limitations"]) for f in findings)


@pytest.mark.parametrize("count", [0, 1, 50])
def test_strings_at_or_under_the_cap_is_not_truncated(count: int, tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    _write_strings(d, [f"https://host{i}.example/x" for i in range(count)])

    findings, coverage, _ = _run(scans, tmp_path)

    assert len(_strings_findings(findings)) == count
    assert coverage["coverage"] == "complete"
    assert coverage["scans"][0]["degraded_steps"] == []


def test_strings_json_over_the_cap_is_partial_too(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    (d / "strings-findings.txt").unlink()
    items = [{"value": f"https://host{i}.example/x"} for i in range(60)]
    (d / "strings-findings.json").write_text(json.dumps({"findings": items}), encoding="utf-8")

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "partial"
    assert any("first 50 of 60" in lim for lim in coverage["scans"][0]["limitations"])


# -- header analysis: junk is not a read result ------------------------------------------------------


def _header(scans: Path, tmp: Path, content: object) -> tuple[list[dict], dict]:
    s = scans / "app" / "2026-10-19"
    s.mkdir(parents=True)
    for step in ("checksec", "yara", "strings"):
        name, body = OUTPUTS[step]
        (s / name).write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")
    (s / "header-analysis.json").write_text(json.dumps(content), encoding="utf-8")
    (s / "scan-meta.json").write_text(json.dumps({"steps": _steps()}), encoding="utf-8")
    findings, coverage, _ = _run(scans, tmp)
    return findings, coverage


JUNK_HEADERS = [
    {"format": "pe", "checks": {}},
    {"format": "banana", "checks": {"signed": False}},
    {"format": "elf", "checks": {"signed": False}},  # a PE check under elf
    {"format": "pe", "checks": {"interpreter_trusted": False}},  # an ELF check under pe
    {"format": "pe", "checks": {"signed": 0}},
    {"format": "pe", "checks": {"signed": None, "debug_symbols_stripped": "false"}},
    {"format": "pe", "checks": {"signed": "no"}},
    {"format": "pe", "checks": {"made_up_check": False}},
    {"format": ["pe"], "checks": {"signed": False}},
    {"format": {"a": 1}, "checks": {"signed": False}},
    {"checks": {"signed": False}},  # no format key
    {"format": "pe", "checks": ["signed"]},
    {"format": "PE", "checks": {"signed": False}},
]


@pytest.mark.parametrize("content", JUNK_HEADERS, ids=lambda c: json.dumps(c)[:50])
def test_junk_header_analysis_is_unread_partial_and_says_why(content: object, tmp_path: Path):
    findings, coverage = _header(tmp_path / "scans", tmp_path, content)

    scan = coverage["scans"][0]
    assert coverage["coverage"] == "partial"
    assert "header_analysis" in scan["unread_steps"]
    assert "header_analysis" not in scan["steps_read"]
    assert not [f for f in findings if f["scanner"] == "header_analysis"]
    # the other three steps still read, and the reason header-analysis.json was refused is named
    assert scan["steps_read"] == ["checksec", "yara", "strings"]
    assert any("header-analysis.json" in lim for lim in scan["limitations"])


def test_header_check_with_a_non_boolean_value_is_reported_not_silently_ignored(tmp_path: Path):
    content = {"format": "pe", "checks": {"signed": False, "debug_symbols_stripped": 0}}

    findings, coverage = _header(tmp_path / "scans", tmp_path, content)

    scan = coverage["scans"][0]
    assert "header_analysis" in scan["steps_read"]
    assert scan["degraded_steps"] == ["header_analysis"]
    assert coverage["coverage"] == "partial"
    assert any(
        "non-boolean" in lim and "debug_symbols_stripped" in lim for lim in scan["limitations"]
    )
    assert {f["rule_id"] for f in findings if f["scanner"] == "header_analysis"} == {
        "BIN-hdr-signed"
    }


def test_header_check_name_the_doc_does_not_list_is_a_medium_finding_but_never_the_read(
    tmp_path: Path,
):
    """Unknown names keep the documented medium finding; they cannot make the step read alone."""
    content = {"format": "pe", "checks": {"signed": True, "zzz_custom": False}}

    findings, coverage = _header(tmp_path / "scans", tmp_path, content)

    scan = coverage["scans"][0]
    custom = [f for f in findings if f["rule_id"] == "BIN-hdr-zzz_custom"]
    assert [f["severity"] for f in custom] == ["medium"]
    assert "header_analysis" in scan["steps_read"]
    assert coverage["coverage"] == "complete"
    assert any("zzz_custom" in lim and "unrecognised" in lim for lim in scan["limitations"])


def test_header_check_names_cannot_inject_control_characters_or_unbounded_text(tmp_path: Path):
    evil = "evil\nname\x1b[31m " + "x" * 5000
    content = {"format": "pe", "checks": {"signed": True, evil: False}}

    findings, coverage = _header(tmp_path / "scans", tmp_path, content)

    (f,) = [f for f in findings if f["scanner"] == "header_analysis"]
    for text in (f["rule_id"], f["message"], f["id"]):
        assert text.isprintable() and "\n" not in text
    assert len(f["rule_id"]) < 100 and len(f["message"]) < 300
    assert all(len(lim) < 1000 and lim.isprintable() for lim in coverage["scans"][0]["limitations"])


# -- result discovery: documented names, top level of the scan directory ------------------------------


def test_stale_result_in_a_subdirectory_is_ignored_and_named(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()}, outputs=("yara", "strings", "header_analysis"))
    old = d / "old"
    old.mkdir()
    (old / "checksec.json").write_text(json.dumps(OUTPUTS["checksec"][1]), encoding="utf-8")

    findings, coverage, _ = _run(scans, tmp_path)

    scan = coverage["scans"][0]
    assert len(coverage["scans"]) == 1
    assert scan["unread_steps"] == ["checksec"]
    assert coverage["coverage"] == "partial"
    assert not [f for f in findings if f["scanner"] == "checksec"]
    assert any(
        "old" in lim and "checksec.json" in lim and "ignored" in lim for lim in scan["limitations"]
    )


@pytest.mark.parametrize(
    ("name", "content", "step"),
    [
        ("checksec-old.json", json.dumps(OUTPUTS["checksec"][1]), "checksec"),
        ("yara-notes.json", json.dumps(OUTPUTS["yara"][1]), "yara"),
        ("strings-notes.txt", "this is prose about password handling\n", "strings"),
        ("header-analysis.bak.json", json.dumps(OUTPUTS["header_analysis"][1]), "header_analysis"),
    ],
)
def test_a_wrongly_named_file_is_not_the_result_of_the_step(
    name: str, content: str, step: str, tmp_path: Path
):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()}, outputs=tuple(s for s in ALL_STEPS if s != step))
    (d / name).write_text(content, encoding="utf-8")

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "partial"
    assert coverage["scans"][0]["unread_steps"] == [step]


def test_a_result_file_holding_another_steps_output_does_not_count_for_its_own(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    (d / "checksec.json").write_text(json.dumps(OUTPUTS["yara"][1]), encoding="utf-8")

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["scans"][0]["unread_steps"] == ["checksec"]


def test_an_empty_list_is_a_clean_yara_result_only_in_the_yara_file(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    (d / "checksec.json").write_text("[]", encoding="utf-8")  # not yara output

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["scans"][0]["unread_steps"] == ["checksec"]


def test_detect_step_reads_an_empty_list_as_yara_only_by_the_yara_name():
    sys.path.insert(0, str(REPO_ROOT))
    import parse_binary

    assert parse_binary.detect_step([], "yara-matches.json") == "yara"
    assert parse_binary.detect_step([], "checksec.json") is None
    assert parse_binary.detect_step([], "") is None
    assert parse_binary.detect_step({"checks": {"signed": True}}, "header-analysis.json") is None
    assert parse_binary.detect_step({"format": "pe", "checks": {}}, "x") == "header_analysis"


@pytest.mark.parametrize("tool", ["", "   ", 5, ["t"], {}, None, True])
def test_a_ran_step_needs_a_real_tool_name(tool):
    steps = _steps()
    steps[0]["tool"] = tool

    report = scan_coverage.assess({"steps": steps}, ALL_STEPS, set(ALL_STEPS))

    assert report["coverage"] == "unknown"
    assert any("without naming the tool" in lim for lim in report["limitations"])


# -- undecodable bytes ----------------------------------------------------------------------------------


def test_strings_with_a_few_undecodable_bytes_are_read_but_partial_and_the_loss_is_named(
    tmp_path: Path,
):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    (d / "strings-findings.txt").write_bytes(b"password=ok\n" * 10 + b"secret=\xff\xfe\xfd\n")

    findings, coverage, _ = _run(scans, tmp_path)

    assert len(_strings_findings(findings)) == 11
    scan = coverage["scans"][0]
    assert "strings" in scan["steps_read"]
    assert coverage["coverage"] == "partial"
    assert scan["degraded_steps"] == ["strings"]
    assert any("3 undecodable byte(s)" in lim for lim in scan["limitations"])


# -- text encodings: Windows tools do not write UTF-8 ---------------------------------------------------

CREDENTIAL_LINES = ["http://internal.example/x", "password=hunter2", "api_key=abcd1234"]
CREDENTIAL_TEXT = "\r\n".join(CREDENTIAL_LINES) + "\r\n"


def _severities(findings: list[dict]) -> list[str]:
    return sorted(f["severity"] for f in findings if f["scanner"] == "strings")


def _strings_as(tmp_path: Path, raw: bytes) -> tuple[list[dict], dict]:
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    (d / "strings-findings.txt").write_bytes(raw)
    findings, coverage, _ = _run(scans, tmp_path)
    return findings, coverage["scans"][0] | {"overall": coverage["coverage"]}


UTF8_SEVERITIES = ["high", "high", "medium"]


@pytest.mark.parametrize(
    ("label", "raw", "named"),
    [
        # what Windows PowerShell 5.1's `>` writes: UTF-16 LE with a BOM and CRLF
        ("utf16-le-bom", b"\xff\xfe" + CREDENTIAL_TEXT.encode("utf-16-le"), "UTF-16"),
        ("utf16-be-bom", b"\xfe\xff" + CREDENTIAL_TEXT.encode("utf-16-be"), "UTF-16"),
        ("utf16-le-no-bom", CREDENTIAL_TEXT.encode("utf-16-le"), "UTF-16"),
        ("utf16-be-no-bom", CREDENTIAL_TEXT.encode("utf-16-be"), "UTF-16"),
        ("utf32-le-bom", b"\xff\xfe\x00\x00" + CREDENTIAL_TEXT.encode("utf-32-le"), "UTF-32"),
        ("utf32-be-bom", b"\x00\x00\xfe\xff" + CREDENTIAL_TEXT.encode("utf-32-be"), "UTF-32"),
        ("utf8-bom", b"\xef\xbb\xbf" + CREDENTIAL_TEXT.encode("utf-8"), "UTF-8 BOM"),
    ],
)
def test_strings_in_another_unicode_encoding_are_decoded_and_the_encoding_is_named(
    label: str, raw: bytes, named: str, tmp_path: Path
):
    """The same three lines must give the same severities as UTF-8, not 4 findings all `info`."""
    findings, scan = _strings_as(tmp_path, raw)

    assert _severities(findings) == UTF8_SEVERITIES, label
    assert "strings" in scan["steps_read"]
    assert scan["overall"] == "complete"  # decoded correctly: a note, not a degradation
    assert any(named in lim and "strings-findings.txt" in lim for lim in scan["limitations"])


def test_the_same_lines_in_utf8_are_the_baseline(tmp_path: Path):
    findings, scan = _strings_as(tmp_path, CREDENTIAL_TEXT.encode("utf-8"))

    assert _severities(findings) == UTF8_SEVERITIES
    assert scan["limitations"] == []


@pytest.mark.parametrize(
    ("label", "raw"),
    [
        ("all-0xff", b"\xff" * 1000),
        ("mostly-bad-bytes", b"password=x\n" + b"\xff\xfe" * 500),
        ("nul-in-utf8-text", b"password=x\n\x00\x00secret=y\n"),
        ("binary-with-nuls", bytes(range(256)) * 4),
    ],
)
def test_strings_that_are_not_text_are_unread_not_complete(label: str, raw: bytes, tmp_path: Path):
    findings, scan = _strings_as(tmp_path, raw)

    assert scan["overall"] == "partial", label
    assert scan["unread_steps"] == ["strings"]
    assert any("strings-findings.txt could not be read" in lim for lim in scan["limitations"])


def test_a_real_replacement_character_is_not_an_undecodable_byte(tmp_path: Path):
    """Counted from the decoder's errors, not from U+FFFD in the output text."""
    raw = ("password=caf�\r\n" * 3).encode("utf-8")

    findings, scan = _strings_as(tmp_path, raw)

    assert len(_strings_findings(findings)) == 3
    assert scan["overall"] == "complete"
    assert scan["limitations"] == []


@pytest.mark.parametrize(
    ("name", "make"),
    [
        ("checksec.json", lambda c: json.dumps(c)),
        ("yara-matches.json", lambda c: json.dumps(c)),
        ("header-analysis.json", lambda c: json.dumps(c)),
    ],
)
@pytest.mark.parametrize(
    ("label", "encode"),
    [
        ("utf8-bom", lambda t: b"\xef\xbb\xbf" + t.encode("utf-8")),
        ("utf16-le-bom", lambda t: b"\xff\xfe" + t.encode("utf-16-le")),
        ("utf16-be-no-bom", lambda t: t.encode("utf-16-be")),
    ],
)
def test_json_results_in_another_encoding_are_read_and_the_encoding_is_named(
    name: str, make, label: str, encode, tmp_path: Path
):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    step = {"checksec.json": "checksec", "yara-matches.json": "yara"}.get(name, "header_analysis")
    (d / name).write_bytes(encode(make(OUTPUTS[step][1])))

    findings, coverage, _ = _run(scans, tmp_path)

    scan = coverage["scans"][0]
    assert step in scan["steps_read"], label
    assert [f for f in findings if f["scanner"] == step]
    assert coverage["coverage"] == "complete"
    assert any(name in lim and ("BOM" in lim or "UTF-16" in lim) for lim in scan["limitations"])


@pytest.mark.parametrize(
    ("label", "encode"),
    [
        ("utf8-bom", lambda t: b"\xef\xbb\xbf" + t.encode("utf-8")),
        ("utf16-le-bom", lambda t: b"\xff\xfe" + t.encode("utf-16-le")),
    ],
)
def test_scan_meta_written_by_a_windows_tool_still_counts(label: str, encode, tmp_path: Path):
    """A BOM or UTF-16 scan-meta.json used to read as unreadable, so the scan went `unknown`."""
    scans = tmp_path / "scans"
    d = _scan(scans, "app", None)
    (d / "scan-meta.json").write_bytes(encode(json.dumps({"steps": _steps()})))

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["coverage"] == "complete", label


def test_a_scan_meta_nested_past_the_recursion_limit_reads_unknown_and_loses_nothing(
    tmp_path: Path,
):
    scans = tmp_path / "scans"
    _scan(scans, "app", '{"steps": ' + "[" * 100_000 + "]" * 100_000 + "}")

    findings, coverage, _ = _run(scans, tmp_path)

    assert {f["scanner"] for f in findings} == set(ALL_STEPS)
    assert coverage["coverage"] == "unknown"


# -- relative and unusual --scans-dir forms -----------------------------------------------------------


def _path_forms(tmp: Path) -> list[tuple[str, str, Path]]:
    scans = tmp / "scans"
    dated = scans / "app" / "2026-10-19"
    forms = [
        ("relative", "scans", tmp),
        ("dot-in-the-scan-dir", ".", dated),
        ("relative-dated-dir", "app/2026-10-19", scans),
        ("relative-dated-dir-dot-slash", "./app/2026-10-19", scans),
        ("dotdot-segments", "scans/app/../app", tmp),
        ("dotdot-out-and-back", "../../../scans", dated),
        ("trailing-slash", str(scans) + "/", tmp),
        ("absolute", str(scans), tmp),
    ]
    if sys.platform == "win32":
        forms += [
            ("trailing-backslash", str(scans) + "\\", tmp),
            ("relative-backslashes", "app\\2026-10-19", scans),
            ("case-differs", str(scans).swapcase(), tmp),
        ]
    return forms


def _form_ids() -> list[str]:
    return [f[0] for f in _path_forms(Path("x"))]


@pytest.mark.parametrize("form", _form_ids())
def test_scans_dir_given_in_any_path_form_gives_the_same_result_as_the_absolute_path(
    form: str, tmp_path: Path
):
    scans = tmp_path / "scans"
    _scan(scans, "app", {"steps": _steps()})
    baseline, base_cov, _ = _run(scans, tmp_path)

    _, arg, cwd = next(f for f in _path_forms(tmp_path) if f[0] == form)
    findings, coverage, stderr = _run(arg, tmp_path, cwd=cwd)

    assert "Traceback" not in stderr
    assert sorted(f["fingerprint"] for f in findings) == sorted(f["fingerprint"] for f in baseline)
    assert coverage["coverage"] == "complete" == base_cov["coverage"]
    assert len(coverage["scans"]) == 1
    assert coverage["scans"][0]["steps_read"] == list(ALL_STEPS)


def test_scans_dir_reached_through_a_link_is_the_same_scan(tmp_path: Path):
    real = tmp_path / "real"
    _scan(real, "app", {"steps": _steps()})
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            pytest.skip("cannot create a symlink here")
        made = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(real)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if made.returncode != 0:
            pytest.skip("cannot create a symlink or junction here")

    findings, coverage, stderr = _run(link, tmp_path)

    assert "Traceback" not in stderr
    assert {f["coverage"] for f in findings} == {"complete"}
    assert len(coverage["scans"]) == 1


def test_split_by_scan_dir_resolves_both_sides_with_an_injected_resolver(tmp_path: Path):
    """Where links cannot be made: a resolver maps an alias prefix onto the real tree."""
    real = tmp_path / "real"
    d = _scan(real, "app", {"steps": _steps()})
    alias = tmp_path / "alias"  # does not exist; only the resolver knows it is `real`

    def resolve(p: Path) -> Path:
        s = str(p)
        return Path(s.replace(str(alias), str(real))) if s.startswith(str(alias)) else p

    candidate = alias / "app" / "2026-10-19" / "checksec.json"
    stale = alias / "app" / "2026-10-19" / "old" / "checksec.json"
    (d / "old").mkdir()
    kept, ignored = scan_coverage.split_by_scan_dir(alias, [candidate, stale], resolve=resolve)

    assert kept == [candidate]
    assert [p for paths in ignored.values() for p in paths] == [stale]


@pytest.mark.parametrize(
    "candidate",
    [Path("checksec.json"), Path("a/b/../checksec.json"), Path("/nonexistent/x/checksec.json")],
)
def test_split_by_scan_dir_never_raises_on_an_odd_path(candidate: Path, tmp_path: Path):
    scan_coverage.split_by_scan_dir(tmp_path, [candidate])
    scan_coverage.split_by_scan_dir(Path("relative/scans"), [candidate])
    scan_coverage.scan_dirs(Path("relative/scans"), [candidate])


def test_an_unexpected_failure_in_discovery_still_writes_the_sidecar(tmp_path: Path, monkeypatch):
    """Whatever goes wrong while reading results ends in a sidecar and exit 1, never a crash."""
    import parse_binary

    scans = tmp_path / "scans"
    _scan(scans, "app", {"steps": _steps()})
    cov = tmp_path / "cov.json"

    def boom(*_a, **_k):
        raise RuntimeError("simulated discovery failure \x1b[31m")

    monkeypatch.setattr(parse_binary.scan_coverage, "split_by_scan_dir", boom)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "parse_binary.py",
            "--client",
            "c",
            "--scans-dir",
            str(scans),
            "--coverage-output",
            str(cov),
        ],
    )
    with pytest.raises(SystemExit) as exit_info:
        parse_binary.main()

    assert exit_info.value.code == 1
    sidecar = json.loads(cov.read_text("utf-8"))
    assert sidecar["coverage"] == "unknown"
    (lim,) = sidecar["scans"][0]["limitations"]
    assert "simulated discovery failure" in lim and "\x1b" not in lim


# -- a file that looks like a result but is not named like one is named -------------------------------------


@pytest.mark.parametrize(
    ("name", "step"),
    [
        ("checksec-old.json", "checksec"),
        ("Checksec.JSON", "checksec"),
        ("yara-notes.json", "yara"),
        ("strings-notes.txt", "strings"),
        ("header-analysis.bak.json", "header_analysis"),
    ],
)
def test_a_wrongly_named_top_level_file_is_named_in_the_limitations(
    name: str, step: str, tmp_path: Path
):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()}, outputs=tuple(s for s in ALL_STEPS if s != step))
    (d / name).write_text("{}", encoding="utf-8")

    _, coverage, _ = _run(scans, tmp_path)

    scan = coverage["scans"][0]
    assert scan["unread_steps"] == [step]
    assert any(name in lim and "was ignored" in lim for lim in scan["limitations"])
    assert not any("see the other limitations" in lim for lim in scan["limitations"])


def test_ordinary_files_in_a_scan_directory_are_not_called_misnamed_results(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    for other in ("scan-meta.bak", "coverage.json", "hash.json", "notes.md", "binary.exe"):
        (d / other).write_text("x", encoding="utf-8")

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["scans"][0]["limitations"] == []


# -- names that collide after cleaning must not lose a finding ---------------------------------------------


def test_header_check_names_that_clean_to_the_same_text_each_keep_their_finding(tmp_path: Path):
    names = ["a", "a\n", "a\x00", "\x07a", "signed"]
    content = {"format": "pe", "checks": {n: False for n in names}}

    findings, _ = _header(tmp_path / "scans", tmp_path, content)

    headers = [f for f in findings if f["scanner"] == "header_analysis"]
    assert len(headers) == 5
    assert len({f["rule_id"] for f in headers}) == 5
    assert len({f["fingerprint"] for f in headers}) == 5


def test_long_header_check_names_with_a_shared_prefix_each_keep_their_finding(tmp_path: Path):
    prefix = "p" * 60
    names = [prefix + "x" * 40, prefix + "y" * 40, "signed"]
    content = {"format": "pe", "checks": {n: False for n in names}}

    findings, _ = _header(tmp_path / "scans", tmp_path, content)

    headers = [f for f in findings if f["scanner"] == "header_analysis"]
    assert len({f["fingerprint"] for f in headers}) == 3


# -- survivors from the third review -------------------------------------------------------------------------


@pytest.mark.parametrize("findings", [5, "password=x", {"a": 1}, None, True])
def test_a_strings_result_whose_findings_is_not_a_list_is_not_a_strings_result(
    findings: object, tmp_path: Path
):
    """A string would otherwise be read as one finding per character."""
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()}, outputs=("checksec", "yara", "header_analysis"))
    (d / "strings-findings.json").write_text(json.dumps({"findings": findings}), encoding="utf-8")

    _, coverage, _ = _run(scans, tmp_path)

    assert coverage["scans"][0]["unread_steps"] == ["strings"]
    assert any(
        "strings-findings.json could not be read" in lim
        for lim in coverage["scans"][0]["limitations"]
    )


def test_directory_comparison_ignores_trailing_separators_and_dot_segments():
    assert scan_coverage._norm("a/b/") == scan_coverage._norm("a/b")
    assert scan_coverage._norm("a/./b") == scan_coverage._norm("a/b")
    assert scan_coverage._norm("a/c/../b") == scan_coverage._norm("a/b")
    assert scan_coverage._norm("a/b") != scan_coverage._norm("a/bb")


@pytest.mark.skipif(sys.platform != "win32", reason="case folding applies to Windows paths")
def test_directory_comparison_folds_case_on_windows():
    assert scan_coverage._norm("C:\\Scans\\App") == scan_coverage._norm("c:\\scans\\app")


def test_short_strips_control_characters_and_bounds_length():
    text = scan_coverage.short("a\nb\x00c\x1b[31md e" + "x" * 500)

    assert text.isprintable() and text.startswith("abc[31mde")
    assert len(text) <= 203


def test_notes_are_capped_and_the_overflow_is_counted(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    for i in range(30):  # 30 stale copies in subdirectories: 30 notes
        sub = d / f"old{i:02d}"
        sub.mkdir()
        (sub / "checksec.json").write_text("{}", encoding="utf-8")

    _, coverage, _ = _run(scans, tmp_path)

    limitations = coverage["scans"][0]["limitations"]
    assert len(limitations) == 21  # 20 notes and the overflow line
    assert limitations[-1] == "... and 10 more notes"


# -- the mode doc and the parser must agree ------------------------------------------------------------


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


def test_documented_result_files_are_the_ones_the_parser_reads():
    """A6/I1 named different files for strings, and A7 stored nothing. Pin doc == parser."""
    text = EXAMPLES.read_text(encoding="utf-8")
    for step, (name, _content) in OUTPUTS.items():
        assert name in text, f"examples.md never names {name}, the file read for {step}"
    assert "strings-findings.json" not in text


def test_doc_tells_the_agent_to_write_utf8_and_says_what_ingest_accepts():
    text = " ".join(EXAMPLES.read_text(encoding="utf-8").split())
    assert "Write every result file as UTF-8" in text
    assert "Out-File -Encoding utf8" in text
    assert "UTF-16" in text and "BOM" in text
    # the claim the doc makes about misnamed files is now true for top-level files too
    assert "`checksec-old.json` is ignored and named" in text


# -- checksec.json: no silent skips (issue #908) ---------------------------------------------------
#
# parse_checksec_json used to drop things without a trace: a non-object entry, a check whose
# value is neither a boolean nor a string, and every binary after the first. Findings for
# valid input do not change; what was dropped is now named (a note when nothing a finding
# could come from was lost, a `degraded` reason, which makes the step partial, when a
# hardening check or a whole binary went unread).


def _checksec_scan(tmp_path: Path, content: object) -> tuple[list[dict], dict]:
    scans = tmp_path / "scans"
    d = _scan(
        scans,
        "app",
        {"schema_version": 1, "steps": _steps()},
        outputs=("yara", "strings", "header_analysis"),
    )
    (d / "checksec.json").write_text(json.dumps(content), encoding="utf-8")
    findings, coverage, _ = _run(scans, tmp_path)
    return findings, coverage["scans"][0]


def _checksec_findings(findings: list[dict]) -> set[tuple[str, str]]:
    return {(f["file"], f["hardening_check"]) for f in findings if f["scanner"] == "checksec"}


def test_valid_checksec_output_is_unchanged_and_stays_complete(tmp_path: Path):
    findings, scan = _checksec_scan(
        tmp_path, {"app.exe": {"nx": "no", "pie": True, "relro": "partial", "canary": "yes"}}
    )
    assert _checksec_findings(findings) == {("app.exe", "nx"), ("app.exe", "relro")}
    assert scan["coverage"] == "complete" and scan["limitations"] == []


def test_a_non_object_entry_is_named_not_skipped_silently(tmp_path: Path):
    findings, scan = _checksec_scan(tmp_path, {"file": {"nx": "no"}, "version": "2.1", "n": 3})
    assert _checksec_findings(findings) == {("file", "nx")}
    text = " ".join(scan["limitations"])
    assert "not an object" in text and "version" in text and "n" in text


def test_a_hardening_check_with_an_unreadable_value_makes_the_step_partial(tmp_path: Path):
    findings, scan = _checksec_scan(
        tmp_path, {"app.exe": {"nx": None, "pie": 0, "relro": ["full"], "canary": "yes"}}
    )
    assert _checksec_findings(findings) == set()  # still never read as a failure
    assert scan["coverage"] == "partial" and scan["degraded_steps"] == ["checksec"]
    text = " ".join(scan["limitations"])
    for name in ("nx", "pie", "relro"):
        assert name in text
    assert "neither true/false nor text" in text


def test_an_unlisted_check_with_an_odd_value_is_a_note_not_a_downgrade(tmp_path: Path):
    """Real checksec output carries counts and sizes beside the checks: naming them must not
    make every real scan partial."""
    findings, scan = _checksec_scan(tmp_path, {"app.exe": {"nx": "yes", "size": 1234, "x": None}})
    assert _checksec_findings(findings) == set()
    assert scan["coverage"] == "complete"
    text = " ".join(scan["limitations"])
    assert "neither true/false nor text" in text and "size" in text


def test_only_the_first_binary_is_read_and_the_rest_are_named(tmp_path: Path):
    findings, scan = _checksec_scan(
        tmp_path,
        {
            "a.exe": {"nx": "no"},
            "b.exe": {"nx": "no", "pie": "no"},
            "c.exe": {"nx": "no"},
        },
    )
    assert _checksec_findings(findings) == {("a.exe", "nx")}  # unchanged for this input
    assert scan["coverage"] == "partial" and scan["degraded_steps"] == ["checksec"]
    text = " ".join(scan["limitations"])
    assert "3 binaries" in text and "a.exe" in text and "b.exe" in text and "c.exe" in text


def test_a_single_binary_next_to_plain_metadata_is_not_degraded(tmp_path: Path):
    findings, scan = _checksec_scan(
        tmp_path, {"version": "2.1", "app.exe": {"nx": "no", "pie": "yes"}}
    )
    assert _checksec_findings(findings) == {("app.exe", "nx")}
    assert scan["coverage"] == "complete"
    # benign envelope metadata is not a downgrade, but it is not dropped silently either
    assert any("not an object" in x and "version" in x for x in scan["limitations"])


def test_in_the_path_keyed_shape_a_non_object_sibling_is_named_not_dropped(tmp_path: Path):
    findings, scan = _checksec_scan(
        tmp_path, {"app.exe": {"nx": "no"}, "note": "from CI", "n": 3, "l": [1], "z": None}
    )
    assert _checksec_findings(findings) == {("app.exe", "nx")}
    assert scan["coverage"] == "complete"
    text = " ".join(scan["limitations"])
    for name in ("note", "n", "l", "z"):
        assert name in text
    assert "not an object" in text


def test_in_the_path_keyed_shape_an_object_with_no_check_key_makes_the_step_partial(
    tmp_path: Path,
):
    """An object next to the binary could have been another binary's checks, under names this
    parser does not know: dropping it silently is the claim `complete` must not rest on."""
    findings, scan = _checksec_scan(
        tmp_path, {"app.exe": {"nx": "no"}, "other.exe": {"mystery": "no"}, "empty.exe": {}}
    )
    assert _checksec_findings(findings) == {("app.exe", "nx")}  # findings unchanged
    assert scan["coverage"] == "partial" and scan["degraded_steps"] == ["checksec"]
    text = " ".join(scan["limitations"])
    assert "no recognised check" in text and "other.exe" in text and "empty.exe" in text


def test_a_sibling_binary_with_only_unlisted_marker_keys_is_counted_as_unread(tmp_path: Path):
    """`cfg` is a listed check but not one of the keys that pick a binary out: a second
    binary carrying only listed checks used to vanish without a trace."""
    findings, scan = _checksec_scan(
        tmp_path, {"a.exe": {"nx": "no"}, "b.exe": {"cfg": "no", "safeseh": "no"}}
    )
    assert _checksec_findings(findings) == {("a.exe", "nx")}  # unchanged: first binary only
    assert scan["coverage"] == "partial"
    text = " ".join(scan["limitations"])
    assert "2 binaries" in text and "b.exe" in text


@pytest.mark.parametrize(
    "spelling", ["NX", "high_entropy_va", "Fortify", "code_sign", "N_X", "can-ary"]
)
def test_a_listed_check_counts_in_any_spelling_when_looking_for_unread_binaries(
    tmp_path: Path, spelling: str
):
    findings, scan = _checksec_scan(tmp_path, {"a.exe": {"nx": "no"}, "b.exe": {spelling: "no"}})
    assert _checksec_findings(findings) == {("a.exe", "nx")}
    text = " ".join(scan["limitations"])
    assert "2 binaries" in text and "no recognised check" not in text


def test_in_the_file_envelope_a_non_object_sibling_is_named_and_objects_are_read(tmp_path: Path):
    findings, scan = _checksec_scan(
        tmp_path, {"file": {"nx": "no"}, "other": {"mystery": "no"}, "version": "2.1"}
    )
    assert _checksec_findings(findings) == {("file", "nx"), ("other", "mystery")}
    text = " ".join(scan["limitations"])
    assert "not an object" in text and "version" in text
    assert scan["coverage"] == "complete"


def test_in_the_unmarked_shape_non_objects_are_named_and_objects_are_read(tmp_path: Path):
    findings, scan = _checksec_scan(tmp_path, {"a.exe": {"cfg": "no"}, "version": "1", "k": 2})
    assert _checksec_findings(findings) == {("a.exe", "cfg")}
    text = " ".join(scan["limitations"])
    assert "not an object" in text and "version" in text and "k" in text
    assert scan["coverage"] == "complete"


# -- short control-character names (issue #908) -----------------------------------------------------


def test_a_check_name_made_only_of_control_characters_is_cleaned_and_kept_distinct():
    sys.path.insert(0, str(ETL))
    sys.path.insert(0, str(REPO_ROOT))
    import parse_binary

    a, b, c = (parse_binary._clean_name(n) for n in ("\x07", "\x01", "\x1b[31m"))
    assert all(x.isprintable() for x in (a, b, c))
    assert a.startswith("?~") and b.startswith("?~")
    assert len({a, b, c}) == 3
    assert parse_binary._clean_name("plain") == "plain"
    assert parse_binary._clean_name("x" * 60) == "x" * 60
    assert parse_binary._clean_name("x" * 61) != "x" * 61 and "~" in parse_binary._clean_name(
        "x" * 61
    )
    assert parse_binary._clean_name("") != "" and "~" in parse_binary._clean_name("")


def test_a_header_check_named_with_a_control_character_gets_a_printable_rule_id(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"schema_version": 1, "steps": _steps()})
    (d / "header-analysis.json").write_text(
        json.dumps({"format": "pe", "checks": {"signed": True, "\x07": False, "\x01": False}}),
        encoding="utf-8",
    )
    findings, _, _ = _run(scans, tmp_path)
    hdr = [f for f in findings if f["scanner"] == "header_analysis"]
    assert len(hdr) == 2 and len({f["rule_id"] for f in hdr}) == 2
    assert all(f["rule_id"].isprintable() and f["message"].isprintable() for f in hdr)


# -- the same finding from two scans keeps the weaker coverage (issue #908) ------------------------


def test_a_yara_finding_in_two_scans_takes_the_weaker_coverage_and_says_so(tmp_path: Path):
    scans = tmp_path / "scans"
    _scan(scans, "app", {"schema_version": 1, "steps": _steps()}, date="2026-10-18")
    _scan(
        scans,
        "app",
        {"schema_version": 1, "steps": _steps(header_analysis="skipped")},
        outputs=("checksec", "yara", "strings"),
        date="2026-10-19",
    )

    findings, coverage, _ = _run(scans / "app", tmp_path)

    yara = [f for f in findings if f["scanner"] == "yara"]
    assert len(yara) == 1 and yara[0]["coverage"] == "partial"
    text = " ".join(yara[0]["limitations"])
    assert "header_analysis" in text and "also reported by another scan" in text
    assert {Path(s["scan_dir"]).name: s["coverage"] for s in coverage["scans"]} == {
        "2026-10-18": "complete",
        "2026-10-19": "partial",
    }
    # a finding only the complete scan has keeps that scan's coverage
    hdr = [f for f in findings if f["scanner"] == "header_analysis"]
    assert [f["coverage"] for f in hdr] == ["complete"]


def test_merging_scans_is_order_independent(tmp_path: Path):
    for first, second in (("complete", "partial"), ("partial", "complete")):
        root = tmp_path / f"{first}-{second}"
        for date, kind in (("2026-10-18", first), ("2026-10-19", second)):
            skipped = {"header_analysis": "skipped"} if kind == "partial" else {}
            _scan(
                root,
                "app",
                {"schema_version": 1, "steps": _steps(**skipped)},
                outputs=("checksec", "yara", "strings") if skipped else ALL_STEPS,
                date=date,
            )
        findings, _, _ = _run(root / "app", tmp_path)
        assert {f["coverage"] for f in findings if f["scanner"] == "yara"} == {"partial"}


def test_doc_describes_unread_exactly_as_the_code_behaves():
    """An empty strings-findings.txt is a result (grep matched nothing), so the doc must not
    list "empty" among the things that make a ran step partial."""
    text = " ".join(EXAMPLES.read_text(encoding="utf-8").split())
    assert "missing, empty" not in text and "empty or unparseable" not in text
    assert "missing or unparseable" in text
    assert "an empty `strings-findings.txt` is a result" in text
    assert "first 50" in text  # the strings cap and its `partial` are documented
