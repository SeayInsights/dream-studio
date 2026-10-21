"""netcompat says `not_assessed` when it did not assess DLP risk; it never says `low`.

WHY (issue #895 item 4). `assess_dlp_risk` returned "low" when the client profile had no
`data.critical` / `data.sensitive` terms, and the CSV, the Power BI card and the report all
read that as "low risk". The mode's own anti-pattern says to skip the assessment and note
it. A repo that was not assessed for DLP risk is not a low-risk repo, so the `dlp_risk`
vocabulary is now `high | medium | low | not_assessed`.

Which readers of `dlp_risk` exist was checked, not assumed: the vocabulary is read by the
Power BI spec (DAX measures and a conditional colour) and by the mode docs; map_compliance,
score_findings, generate_mitigations and export_dataset do not read the column, which a
test below pins so a new reader has to decide what `not_assessed` means to it.
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
SCRIPT = ETL / "analyze_netcompat.py"
MODES = REPO_ROOT / "canonical" / "skills" / "security" / "modes"
SPEC = REPO_ROOT / "templates" / "security" / "powerbi" / "dashboard-spec.md"

sys.path.insert(0, str(ETL))
import analyze_netcompat as nc  # noqa: E402


def _result(rule: str, path: str, text: str = "outbound call") -> dict:
    return {
        "ruleId": rule,
        "message": {"text": text},
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": path}}}],
    }


def test_no_terms_is_not_assessed_not_low() -> None:
    findings = [_result("acme-zsc-004", "repo/app.py")]
    assert nc.assess_dlp_risk(findings, []) == nc.DLP_NOT_ASSESSED
    assert nc.DLP_NOT_ASSESSED == "not_assessed"


def test_terms_present_keep_their_documented_values() -> None:
    hit = [_result("acme-zsc-004", "repo/app.py", "sends ssn to host")]
    near = [_result("acme-zsc-004", "repo/ssn-service/app.py")]
    none = [_result("acme-zsc-004", "repo/app.py")]
    assert nc.assess_dlp_risk(hit, ["SSN"]) == "high"
    assert nc.assess_dlp_risk(near, ["ssn"]) == "high"  # the path contains the term
    assert nc.assess_dlp_risk(none, ["SSN"]) == "low"
    assert nc.assess_dlp_risk([], ["SSN"]) == "low"  # assessed, and nothing to match


def test_score_repo_row_carries_not_assessed() -> None:
    row = nc.score_repo("repo", [_result("acme-zsc-001", "repo/a.py")], "zscaler", [])
    assert row["dlp_risk"] == "not_assessed"
    assert row["zscaler_score"] == 80  # the score itself is unaffected


def _profile(data: object) -> dict:
    profile: dict = {"network": {"proxy": {"type": "zscaler"}}}
    if data is not None:
        profile["data"] = data
    return profile


@pytest.mark.parametrize(
    "data",
    [None, {}, {"critical": [], "sensitive": []}, {"critical": None, "sensitive": None}],
    ids=["no-data-key", "empty-data", "empty-lists", "null-lists"],
)
def test_run_analysis_without_data_terms_never_reports_low(tmp_path: Path, data: object) -> None:
    sarif_dir = tmp_path / "scans" / "repo-a" / "2026-10-01"
    sarif_dir.mkdir(parents=True)
    sarif = {"runs": [{"results": [_result("acme-zsc-001", "repo-a/a.py")]}]}
    (sarif_dir / "semgrep.sarif").write_text(json.dumps(sarif), encoding="utf-8")
    rows = nc.run_analysis(tmp_path / "scans", _profile(data), extra_repos=["repo-b"])
    assert {r["repo"]: r["dlp_risk"] for r in rows} == {
        "repo-a": "not_assessed",
        "repo-b": "not_assessed",
    }


def test_a_repo_with_no_scan_is_not_assessed_even_when_terms_exist(tmp_path: Path) -> None:
    (tmp_path / "scans").mkdir()
    profile = _profile({"critical": ["ssn"], "sensitive": []})
    rows = nc.run_analysis(tmp_path / "scans", profile, extra_repos=["unscanned"])
    assert rows == [
        {
            "repo": "unscanned",
            "zscaler_score": 100,
            "cert_pinning": 0,
            "dlp_risk": "not_assessed",
            "port_issues": 0,
            "fixes_needed": 0,
        }
    ]


@pytest.mark.parametrize("terms", [[""], ["", "  "], ["\t", "\n"], [None, 3, " "]])
def test_blank_terms_are_not_terms(terms: list) -> None:
    """A blank term is a substring of every message, so it used to match everything and read
    `high`, and a list of blanks counted as an assessment."""
    findings = [_result("acme-zsc-004", "repo/app.py", "plain outbound call")]
    assert nc.assess_dlp_risk(findings, terms) == nc.DLP_NOT_ASSESSED


def test_a_blank_term_beside_a_real_one_is_ignored_not_a_match_for_everything() -> None:
    findings = [_result("acme-zsc-004", "repo/app.py", "plain outbound call")]
    assert nc.assess_dlp_risk(findings, ["", "  ssn "]) == "low"  # real term checked, no hit
    hit = [_result("acme-zsc-004", "repo/app.py", "posts SSN=123 to host")]
    assert nc.assess_dlp_risk(hit, ["", " ssn "]) == "high"  # and the real term still matches


@pytest.mark.parametrize(
    "data",
    [
        {"critical": ["", "  "], "sensitive": [" "]},
        None,
        "ssn",
        ["ssn"],
        7,
        {"critical": "ssn", "sensitive": None},
        {"critical": {"a": 1}, "sensitive": 3},
    ],
    ids=["all-blank", "null", "string", "list", "number", "string-term", "mapping-term"],
)
def test_a_malformed_data_section_is_not_assessed_with_a_note_not_a_crash(
    tmp_path: Path, data: object, capsys
) -> None:
    sarif_dir = tmp_path / "scans" / "repo-a" / "2026-10-01"
    sarif_dir.mkdir(parents=True)
    sarif = {"runs": [{"results": [_result("acme-zsc-001", "repo-a/a.py", "sends ssn")]}]}
    (sarif_dir / "semgrep.sarif").write_text(json.dumps(sarif), encoding="utf-8")
    profile: dict = {"network": {"proxy": {"type": "zscaler"}}, "data": data}
    rows = nc.run_analysis(tmp_path / "scans", profile)
    assert [r["dlp_risk"] for r in rows] == ["not_assessed"]
    err = capsys.readouterr().err
    assert "DLP risk not assessed" in err
    if data not in (None, {"critical": ["", "  "], "sensitive": [" "]}):
        assert "data" in err and ("not a list" in err or "not a mapping" in err)


def test_a_term_given_as_a_bare_string_is_a_problem_to_name_not_a_term_to_guess(
    tmp_path: Path, capsys
) -> None:
    """`critical: ssn` is a scalar where a list belongs; do not guess (the doc: never guess at
    data classifications) and do not iterate its characters."""
    (tmp_path / "scans").mkdir()
    nc.run_analysis(tmp_path / "scans", _profile({"critical": "ssn"}))
    err = capsys.readouterr().err
    assert "data.critical is not a list" in err


def test_the_cli_writes_not_assessed_to_the_csv(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / "clients").mkdir(parents=True)
    (home / "clients" / "acme.yaml").write_text(
        "client:\n  name: Acme\nnetwork:\n  proxy:\n    type: zscaler\n", encoding="utf-8"
    )
    scan = home / "security" / "scans" / "acme" / "repo-a" / "2026-10-01"
    scan.mkdir(parents=True)
    sarif = {"runs": [{"results": [_result("acme-zsc-001", "repo-a/a.py")]}]}
    (scan / "semgrep.sarif").write_text(json.dumps(sarif), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--client", "acme"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "DREAM_STUDIO_HOME": str(home)},
    )
    assert proc.returncode == 0, proc.stderr
    out = home / "security" / "datasets" / "acme" / "netcompat.csv"
    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["dlp_risk"] for r in rows] == ["not_assessed"]
    assert "not assessed" in proc.stderr.lower()  # the note the mode doc asks for


def test_the_vocabulary_is_documented_wherever_dlp_risk_is_listed() -> None:
    for doc in (
        MODES / "netcompat" / "examples.md",
        MODES / "dashboard" / "examples.md",
        SPEC,
    ):
        assert "not_assessed" in doc.read_text(encoding="utf-8"), doc.name
    examples = (MODES / "netcompat" / "examples.md").read_text(encoding="utf-8")
    assert "write `dlp_risk=not_assessed` for every repo" in examples
    assert "`high` / `medium` / `low` / `not_assessed`" in examples
    flat = " ".join(examples.split())
    assert "Blank terms are ignored" in flat and "`critical: ssn`" in flat
    skill = (MODES / "netcompat" / "SKILL.md").read_text(encoding="utf-8")
    assert "dlp_risk=not_assessed" in skill and re.search(r"never `low`", skill)


def test_the_power_bi_card_counts_not_assessed_separately_from_low() -> None:
    spec = SPEC.read_text(encoding="utf-8")
    assert 'Netcompat[dlp_risk] = "not_assessed"' in spec
    assert "DLP Not Assessed Repos" in spec
    assert '"not_assessed" → grey' in spec


def test_no_other_etl_script_reads_dlp_risk() -> None:
    readers = [
        p.name
        for p in ETL.glob("*.py")
        if "dlp_risk" in p.read_text(encoding="utf-8") and p.name != "analyze_netcompat.py"
    ]
    assert readers == []
