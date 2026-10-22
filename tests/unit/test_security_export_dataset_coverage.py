"""export_dataset.py carries a finding's coverage and limitations into findings.csv.

WHY (issue #895 item 3). The parsers stamp every finding with `coverage` (complete |
partial | unknown) and `limitations` (strings naming what the result cannot establish).
`export_dataset.py` writes a fixed column list, and that list omitted both, so a partial
scan reached the CSV datasets and the Power BI report that reads them as an ordinary,
complete-looking finding. The columns are appended (never inserted), so a reader that
addresses columns by position or by name keeps working.

The rule these tests hold: a finding that carries no coverage reads `unknown` in the CSV,
never blank and never `complete`; limitations travel as one JSON string cell.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORT = REPO_ROOT / "templates" / "security" / "etl" / "export_dataset.py"

sys.path.insert(0, str(EXPORT.parent))
import export_dataset  # noqa: E402


def _finding(**extra: object) -> dict:
    base = {"id": "f1", "repo": "r", "severity": "high", "rule_id": "X-1", "message": "m"}
    base.update(extra)
    return base


def _export(tmp_path: Path, findings: list[dict]) -> tuple[list[dict], dict]:
    out = tmp_path / "out"
    env = {**os.environ, "DREAM_STUDIO_HOME": str(tmp_path / "home")}
    proc = subprocess.run(
        [sys.executable, str(EXPORT), "--client", "acme", "--output-dir", str(out)],
        input=json.dumps(findings),
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    with open(out / "findings.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    return rows, meta


def test_partial_coverage_and_limitations_reach_the_csv(tmp_path: Path) -> None:
    limits = ["yara skipped: yara is not installed", 'quote " and, comma']
    rows, _ = _export(tmp_path, [_finding(coverage="partial", limitations=limits)])
    assert rows[0]["coverage"] == "partial"
    assert json.loads(rows[0]["limitations"]) == limits


def test_a_finding_without_coverage_reads_unknown_never_certain(tmp_path: Path) -> None:
    rows, _ = _export(tmp_path, [_finding()])
    assert rows[0]["coverage"] == "unknown"
    stated = json.loads(rows[0]["limitations"])
    assert stated and "not recorded" in stated[0]


def test_blank_or_unrecognised_coverage_reads_unknown(tmp_path: Path) -> None:
    rows, _ = _export(
        tmp_path,
        [
            _finding(id="a", coverage=""),
            _finding(id="b", coverage=None),
            _finding(id="c", coverage="Complete-ish"),
            _finding(id="d", coverage=["complete"]),
        ],
    )
    assert [r["coverage"] for r in rows] == ["unknown"] * 4


def test_complete_is_kept_and_a_scalar_limitation_becomes_a_list(tmp_path: Path) -> None:
    rows, _ = _export(
        tmp_path,
        [
            _finding(id="a", coverage="complete", limitations=[]),
            _finding(id="b", coverage="partial", limitations="one string"),
        ],
    )
    assert rows[0]["coverage"] == "complete"
    assert json.loads(rows[0]["limitations"]) == []
    assert json.loads(rows[1]["limitations"]) == ["one string"]


def test_the_columns_are_appended_so_existing_readers_keep_their_positions() -> None:
    fields = export_dataset.FINDINGS_FIELDS
    assert fields[-2:] == ["coverage", "limitations"]
    assert fields[-3] == "binary_hash"


def test_metadata_reports_the_weakest_coverage_of_what_was_exported(tmp_path: Path) -> None:
    _, meta = _export(
        tmp_path,
        [_finding(id="a", coverage="complete"), _finding(id="b", coverage="partial")],
    )
    assert meta["coverage"] == "partial"


def test_metadata_coverage_is_unknown_when_nothing_states_it(tmp_path: Path) -> None:
    _, meta = _export(tmp_path, [_finding(id="a", coverage="complete"), _finding(id="b")])
    assert meta["coverage"] == "unknown"
    _, empty = _export(tmp_path / "e", [])
    assert empty["coverage"] == "unknown"


# -- a limitations cell must fit a spreadsheet cell (issue #908) ----------------------------------------


EXCEL_CELL_LIMIT = 32_767


def test_a_huge_limitations_list_is_truncated_with_an_explicit_marker(tmp_path: Path) -> None:
    limits = [f"limitation number {i}: " + "x" * 150 for i in range(3000)]  # ~540 KB as JSON
    rows, _ = _export(tmp_path, [_finding(coverage="partial", limitations=limits)])
    cell = rows[0]["limitations"]
    assert len(cell) <= EXCEL_CELL_LIMIT
    kept = json.loads(cell)  # still valid JSON, still a list
    assert kept[0] == limits[0] and kept[:-1] == limits[: len(kept) - 1]
    omitted = len(limits) - (len(kept) - 1)
    assert omitted > 0
    assert kept[-1] == f"... {omitted} more limitation(s) omitted: the cell limit of a spreadsheet"


def test_a_limitations_list_that_fits_is_exported_unchanged(tmp_path: Path) -> None:
    limits = [f"limitation {i}" for i in range(50)]
    rows, _ = _export(tmp_path, [_finding(coverage="partial", limitations=limits)])
    assert json.loads(rows[0]["limitations"]) == limits


def test_the_cell_cap_helper_never_exceeds_the_limit_at_the_edges() -> None:
    for count in (1, 2, 149, 150, 151, 400, 5000):
        limits = ["y" * 200] * count
        cell = export_dataset.limitations_cell(limits)
        assert len(cell) <= EXCEL_CELL_LIMIT, count
        json.loads(cell)


# -- targets the scans never reached (issue #908) --------------------------------------------------------


def _scans(tmp_path: Path) -> Path:
    scans = tmp_path / "home" / "security" / "scans" / "acme"
    real = scans / "web" / "2026-10-19"
    real.mkdir(parents=True)
    (real / "scan-meta.json").write_text(json.dumps({"steps": []}), encoding="utf-8")
    sidecar = json.dumps({"coverage": "complete", "scans": []})
    (real / "coverage.json").write_text(sidecar, encoding="utf-8")
    return scans


def _not_scanned(scans: Path, target: str, day: str, reason: str = "target unreachable") -> None:
    d = scans / target / f"{day}-not-scanned"
    d.mkdir(parents=True)
    meta = {"outcome": "Not_Scanned", "reason": reason, "url": f"https://{target}.example.test"}
    (d / "scan-meta.json").write_text(json.dumps(meta), encoding="utf-8")


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_a_whole_target_that_was_not_scanned_downgrades_the_dataset(tmp_path: Path) -> None:
    scans = _scans(tmp_path)
    _not_scanned(scans, "legacy-admin", "2026-10-20", "zap is not installed (run stopped)")
    findings = [_finding(id="a", repo="web", target_name="web", coverage="complete")]
    _, meta = _export(tmp_path, findings)
    assert meta["coverage"] == "partial"  # every finding is complete; one target was never scanned
    assert meta["not_scanned_targets"] == [
        {
            "target": "legacy-admin",
            "date": "2026-10-20-not-scanned",
            "reason": "zap is not installed (run stopped)",
        }
    ]
    targets = {r["name"]: r for r in _read_csv(tmp_path / "out" / "targets.csv")}
    assert targets["legacy-admin"]["coverage"] == "partial"
    assert targets["legacy-admin"]["finding_count"] == "0"
    assert targets["legacy-admin"]["url"] == "https://legacy-admin.example.test"


def test_a_not_scanned_record_superseded_by_a_later_scan_is_not_reported(tmp_path: Path) -> None:
    scans = _scans(tmp_path)
    _not_scanned(scans, "web", "2026-10-10")  # older than the real 2026-10-19 scan of `web`
    _, meta = _export(tmp_path, [_finding(coverage="complete")])
    assert meta["coverage"] == "complete" and meta["not_scanned_targets"] == []


def test_a_not_scanned_record_the_same_day_as_a_scan_is_the_latest_attempt(tmp_path: Path) -> None:
    scans = _scans(tmp_path)
    _not_scanned(scans, "web", "2026-10-19")  # sorts after the real scan of that day
    _, meta = _export(tmp_path, [_finding(coverage="complete")])
    assert meta["coverage"] == "partial"
    assert [t["target"] for t in meta["not_scanned_targets"]] == ["web"]


def test_a_partial_sidecar_downgrades_even_a_dataset_with_no_findings(tmp_path: Path) -> None:
    scans = _scans(tmp_path)
    (scans / "web" / "2026-10-19" / "coverage.json").write_text(
        json.dumps({"coverage": "partial", "scans": []}), encoding="utf-8"
    )
    _, meta = _export(tmp_path, [])
    assert meta["coverage"] == "partial"


def test_a_complete_sidecar_and_no_findings_is_complete_not_unknown(tmp_path: Path) -> None:
    _scans(tmp_path)
    _, meta = _export(tmp_path, [])
    assert meta["coverage"] == "complete"


@pytest.mark.parametrize(
    "content",
    ["{ not json", json.dumps({"coverage": "fine"}), json.dumps(["complete"]), json.dumps({}), ""],
    ids=["not-json", "outside-the-vocabulary", "not-an-object", "no-coverage-key", "empty"],
)
def test_a_junk_sidecar_is_unknown_not_a_crash_and_not_complete(
    tmp_path: Path, content: str
) -> None:
    scans = _scans(tmp_path)
    (scans / "web" / "2026-10-19" / "coverage.json").write_text(content, encoding="utf-8")
    _, meta = _export(tmp_path, [_finding(coverage="complete")])
    assert meta["coverage"] == "unknown"


def test_a_missing_default_scans_directory_reads_unknown_with_the_reason(tmp_path: Path) -> None:
    """It used to change nothing, so a store that was never written (or a wrong client name)
    hid every unscanned target behind complete findings."""
    _, meta = _export(tmp_path, [_finding(coverage="complete")])
    assert meta["coverage"] == "unknown" and meta["not_scanned_targets"] == []
    assert any("scan store not found" in x for x in meta["limitations"])


def test_scans_dir_can_be_given(tmp_path: Path) -> None:
    scans = tmp_path / "elsewhere"
    _not_scanned(scans, "x", "2026-10-01")
    out = tmp_path / "out"
    proc = subprocess.run(
        [
            sys.executable,
            str(EXPORT),
            "--client",
            "acme",
            "--output-dir",
            str(out),
            "--scans-dir",
            str(scans),
        ],
        input=json.dumps([_finding(coverage="complete")]),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "DREAM_STUDIO_HOME": str(tmp_path / "home")},
    )
    assert proc.returncode == 0, proc.stderr
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    assert [t["target"] for t in meta["not_scanned_targets"]] == ["x"]


# -- repos.csv and targets.csv carry coverage (issue #908) -----------------------------------------------


def test_repos_and_targets_carry_the_weakest_coverage_of_their_findings(tmp_path: Path) -> None:
    findings = [
        _finding(id="a", repo="r1", target_name="t1", coverage="complete"),
        _finding(id="b", repo="r1", target_name="t1", coverage="partial"),
        _finding(id="c", repo="r2", target_name="t2", coverage="complete"),
        _finding(id="d", repo="r3", target_name="t3"),  # states nothing
    ]
    _export(tmp_path, findings)
    repos = {r["name"]: r["coverage"] for r in _read_csv(tmp_path / "out" / "repos.csv")}
    targets = {r["name"]: r["coverage"] for r in _read_csv(tmp_path / "out" / "targets.csv")}
    assert repos == {"r1": "partial", "r2": "complete", "r3": "unknown"}
    assert targets == {"t1": "partial", "t2": "complete", "t3": "unknown"}


def test_the_new_repos_and_targets_columns_are_appended() -> None:
    assert export_dataset.REPOS_FIELDS[-1] == "coverage"
    assert export_dataset.REPOS_FIELDS[-2] == "low_count"
    assert export_dataset.TARGETS_FIELDS[-1] == "coverage"
    assert export_dataset.TARGETS_FIELDS[-2] == "finding_count"


# -- the Power BI query survives a dataset written before these columns (issue #908) ----------------


def test_the_power_bi_query_tolerates_a_findings_csv_without_the_new_columns() -> None:
    spec = (REPO_ROOT / "templates" / "security" / "powerbi" / "dashboard-spec.md").read_text(
        encoding="utf-8"
    )
    query = spec.split("## M-Query: Data Source Configuration")[1].split("For metadata.json")[0]
    assert 'Table.HasColumns(PromotedHeaders, "coverage")' in query
    assert 'Table.HasColumns(WithCoverage, "limitations")' in query
    assert '"unknown"' in query  # an older dataset reads unknown, not blank and not complete
    # the typed-columns step reads the tolerant table, not the raw one
    typed = query.split("TypedColumns = Table.TransformColumnTypes(")[1].split(",")[0]
    assert typed.strip() == "WithLimitations"


def test_the_dashboard_doc_describes_the_scan_store_inputs_and_the_new_columns() -> None:
    doc = (
        REPO_ROOT / "canonical" / "skills" / "security" / "modes" / "dashboard" / "examples.md"
    ).read_text(encoding="utf-8")
    flat = " ".join(doc.split())
    assert "not_scanned_targets" in flat and "`--scans-dir`" in flat
    assert "{date}-not-scanned" in flat and "32,767" in flat
    assert "| coverage | string | Weakest `coverage` of this repo's findings" in doc
    spec = (REPO_ROOT / "templates" / "security" / "powerbi" / "dashboard-spec.md").read_text(
        encoding="utf-8"
    )
    assert "Metadata.not_scanned_targets" in spec and "Targets.coverage" in spec
