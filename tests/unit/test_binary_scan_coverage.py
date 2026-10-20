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


def _run(scans: Path, tmp: Path, *, rc: int = 0) -> tuple[list[dict] | None, dict | None, str]:
    """Run parse_binary.py; (findings, coverage sidecar, stderr). Absent outputs are None."""
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


def test_strings_with_undecodable_bytes_are_still_read_and_the_loss_is_named(tmp_path: Path):
    scans = tmp_path / "scans"
    d = _scan(scans, "app", {"steps": _steps()})
    (d / "strings-findings.txt").write_bytes(b"password=ok\nsecret=\xff\xfe\xfd\n")

    findings, coverage, _ = _run(scans, tmp_path)

    assert len(_strings_findings(findings)) == 2
    scan = coverage["scans"][0]
    assert "strings" in scan["steps_read"]
    assert any("undecodable" in lim and "3" in lim for lim in scan["limitations"])


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


def test_doc_describes_unread_exactly_as_the_code_behaves():
    """An empty strings-findings.txt is a result (grep matched nothing), so the doc must not
    list "empty" among the things that make a ran step partial."""
    text = " ".join(EXAMPLES.read_text(encoding="utf-8").split())
    assert "missing, empty" not in text and "empty or unparseable" not in text
    assert "missing or unparseable" in text
    assert "an empty `strings-findings.txt` is a result" in text
    assert "first 50" in text  # the strings cap and its `partial` are documented
