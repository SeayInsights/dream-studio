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
