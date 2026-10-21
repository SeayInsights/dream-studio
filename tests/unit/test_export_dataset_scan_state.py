"""export_dataset reads the scan store's latest attempt per target, and nothing hides it.

WHY (#908 follow-ups). `scan_state` decides what the dataset's `coverage` says about the
scans themselves (the findings cannot show a target nothing was scanned for). Four ways it
read "no information" as if it were information, or let the wrong thing win:

  * a corrupt newest scan-meta.json was ignored, and a newest directory with neither a
    scan-meta.json nor a coverage.json was ignored: the latest attempt on that target was
    unreadable or left no evidence, and the dataset still read complete;
  * a directory named `latest` or `backup` sorts after the dates, so it shadowed a real
    not-scanned record. Only the documented `{date}` and `{date}-not-scanned` names are
    attempts; anything else is reported as an unrecognised scan directory and shadows nothing;
  * a missing or invalid `--scans-dir`, or an empty default, was silently "no information",
    so a typo hid every unscanned target. An explicit one that is not a directory is an
    error; an absent or empty default is reported in the metadata as coverage `unknown`,
    with the reason;
  * repos.csv said `complete` for a webapp whose latest attempt scanned nothing while
    targets.csv said `partial`. Both now derive a name's coverage from its latest attempt.

Each test runs the real script as a subprocess against a store built in a temp directory.
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
    base = {
        "id": "f1",
        "repo": "web",
        "target_name": "web",
        "severity": "high",
        "rule_id": "X-1",
        "message": "m",
        "coverage": "complete",
    }
    base.update(extra)
    return base


def _run(
    tmp_path: Path, findings: list[dict], *extra: str
) -> tuple[subprocess.CompletedProcess, Path]:
    out = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, str(EXPORT), "--client", "acme", "--output-dir", str(out), *extra],
        input=json.dumps(findings),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "DREAM_STUDIO_HOME": str(tmp_path / "home")},
    )
    return proc, out


def _meta(tmp_path: Path, findings: list[dict], *extra: str) -> dict:
    proc, out = _run(tmp_path, findings, *extra)
    assert proc.returncode == 0, proc.stderr
    return json.loads((out / "metadata.json").read_text(encoding="utf-8"))


def _store(tmp_path: Path) -> Path:
    """The default scan store, with one good scan of `web`."""
    scans = tmp_path / "home" / "security" / "scans" / "acme"
    good = scans / "web" / "2026-10-19"
    good.mkdir(parents=True, exist_ok=True)
    (good / "scan-meta.json").write_text(json.dumps({"steps": []}), encoding="utf-8")
    (good / "coverage.json").write_text(
        json.dumps({"coverage": "complete", "scans": []}), encoding="utf-8"
    )
    return scans


def _attempt(scans: Path, target: str, name: str, *, meta=None, sidecar=None) -> Path:
    d = scans / target / name
    d.mkdir(parents=True, exist_ok=True)
    if meta is not None:
        text = meta if isinstance(meta, str) else json.dumps(meta)
        (d / "scan-meta.json").write_text(text, encoding="utf-8")
    if sidecar is not None:
        text = sidecar if isinstance(sidecar, str) else json.dumps(sidecar)
        (d / "coverage.json").write_text(text, encoding="utf-8")
    return d


NOT_SCANNED = {"outcome": "not_scanned", "reason": "target unreachable"}


def _read(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# -- the latest attempt that is unreadable, or left no evidence ------------------------------------------


def test_a_corrupt_newest_scan_meta_reads_unknown_never_complete(tmp_path: Path) -> None:
    scans = _store(tmp_path)
    _attempt(scans, "web", "2026-10-20", meta="{ not json", sidecar={"coverage": "complete"})
    meta = _meta(tmp_path, [_finding()])
    assert meta["coverage"] == "unknown"
    assert any("web" in x and "2026-10-20" in x and "unreadable" in x for x in meta["limitations"])


@pytest.mark.parametrize("content", ["", "[]", "3", '"text"'])
def test_a_newest_scan_meta_that_is_not_an_object_is_unreadable(
    tmp_path: Path, content: str
) -> None:
    scans = _store(tmp_path)
    _attempt(scans, "web", "2026-10-20", meta=content)
    assert _meta(tmp_path, [_finding()])["coverage"] == "unknown"


def test_a_newest_directory_with_no_meta_and_no_sidecar_reads_unknown(tmp_path: Path) -> None:
    scans = _store(tmp_path)
    _attempt(scans, "web", "2026-10-20")  # an empty directory: nothing says what happened
    meta = _meta(tmp_path, [_finding()])
    assert meta["coverage"] == "unknown"
    assert any("2026-10-20" in x and "no scan-meta.json" in x for x in meta["limitations"])


def test_a_readable_meta_with_no_sidecar_is_unknown_not_complete(tmp_path: Path) -> None:
    scans = _store(tmp_path)
    _attempt(scans, "web", "2026-10-20", meta={"steps": []})
    meta = _meta(tmp_path, [_finding()])
    assert meta["coverage"] == "unknown"
    assert any("coverage.json" in x for x in meta["limitations"])


def test_a_sidecar_with_no_meta_still_states_its_coverage(tmp_path: Path) -> None:
    scans = _store(tmp_path)
    _attempt(scans, "web", "2026-10-20", sidecar={"coverage": "partial", "scans": []})
    assert _meta(tmp_path, [_finding()])["coverage"] == "partial"


def test_a_target_whose_only_directories_are_unrecognised_reads_unknown(tmp_path: Path) -> None:
    scans = _store(tmp_path)
    (scans / "orphan" / "latest").mkdir(parents=True)
    meta = _meta(tmp_path, [_finding()])
    assert meta["coverage"] == "unknown"
    assert any("orphan" in x and "no recognised scan directory" in x for x in meta["limitations"])


def test_an_older_bad_attempt_does_not_matter_once_a_later_good_one_exists(
    tmp_path: Path,
) -> None:
    scans = _store(tmp_path)
    _attempt(scans, "web", "2026-10-01", meta="{ not json")
    meta = _meta(tmp_path, [_finding()])
    assert meta["coverage"] == "complete" and meta["limitations"] == []


# -- directory names -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["latest", "backup", "zzz", "2026-10-19-old", "2026-13-45", "tmp"])
def test_an_unrecognised_directory_is_reported_and_shadows_nothing(
    tmp_path: Path, name: str
) -> None:
    scans = _store(tmp_path)
    _attempt(scans, "legacy", "2026-10-20-not-scanned", meta=NOT_SCANNED)
    _attempt(scans, "legacy", name, meta={"steps": []}, sidecar={"coverage": "complete"})
    meta = _meta(tmp_path, [_finding()])
    # the real not-scanned record still decides, not the lexically later directory
    assert [t["target"] for t in meta["not_scanned_targets"]] == ["legacy"]
    assert meta["coverage"] == "partial"
    assert f"unrecognised scan directory legacy/{name}" in meta["limitations"]


def test_an_unrecognised_directory_next_to_a_good_scan_changes_only_the_limitations(
    tmp_path: Path,
) -> None:
    scans = _store(tmp_path)
    (scans / "web" / "latest").mkdir()
    (scans / "web" / "backup").mkdir()
    meta = _meta(tmp_path, [_finding()])
    assert meta["coverage"] == "complete"
    assert meta["limitations"] == [
        "unrecognised scan directory web/backup",
        "unrecognised scan directory web/latest",
    ]


def test_only_the_documented_names_are_attempts() -> None:
    ok = ["2026-10-19", "2026-10-19-not-scanned", "1999-01-01", "2026-02-28"]
    bad = [
        "2026-10-19-not-scanned-2",
        "2026-2-3",
        "2026-02-30",
        "latest",
        "2026-10-19 ",
        "x2026-10-19",
    ]
    for name in ok:
        assert export_dataset.attempt_key(name) is not None, name
    for name in bad:
        assert export_dataset.attempt_key(name) is None, name
    # a not-scanned record sorts after a scan of the same day and before the next day's
    names = ["2026-10-20", "2026-10-19-not-scanned", "2026-10-19", "2026-10-18-not-scanned"]
    assert sorted(names, key=export_dataset.attempt_key) == [
        "2026-10-18-not-scanned",
        "2026-10-19",
        "2026-10-19-not-scanned",
        "2026-10-20",
    ]
    assert export_dataset.attempt_key("2026-10-19") < export_dataset.attempt_key(
        "2026-10-19-not-scanned"
    )


# -- the scan store itself ------------------------------------------------------------------------------------


def test_an_explicit_scans_dir_that_does_not_exist_is_an_error(tmp_path: Path) -> None:
    proc, out = _run(tmp_path, [_finding()], "--scans-dir", str(tmp_path / "typo"))
    assert proc.returncode != 0
    assert "--scans-dir" in proc.stderr and "does not exist" in proc.stderr
    assert str(tmp_path / "typo") in proc.stderr
    assert "Traceback" not in proc.stderr
    assert not (out / "metadata.json").exists()  # nothing was written on the way out


def test_an_explicit_scans_dir_that_is_a_file_is_an_error(tmp_path: Path) -> None:
    afile = tmp_path / "a-file"
    afile.write_text("x", encoding="utf-8")
    proc, out = _run(tmp_path, [_finding()], "--scans-dir", str(afile))
    assert proc.returncode != 0
    assert "not a directory" in proc.stderr
    assert not (out / "metadata.json").exists()


def test_an_absent_default_store_reads_unknown_with_the_reason(tmp_path: Path) -> None:
    meta = _meta(tmp_path, [_finding()])  # nothing under the home at all
    assert meta["coverage"] == "unknown"
    assert any("scan store not found" in x for x in meta["limitations"])
    assert meta["not_scanned_targets"] == []


def test_an_empty_default_store_reads_unknown_with_the_reason(tmp_path: Path) -> None:
    (tmp_path / "home" / "security" / "scans" / "acme").mkdir(parents=True)
    meta = _meta(tmp_path, [_finding()])
    assert meta["coverage"] == "unknown"
    assert any("no target directories" in x for x in meta["limitations"])


def test_an_explicit_empty_scans_dir_reads_unknown_too(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    meta = _meta(tmp_path, [_finding()], "--scans-dir", str(empty))
    assert meta["coverage"] == "unknown"


def test_a_partial_finding_still_beats_the_missing_store(tmp_path: Path) -> None:
    assert _meta(tmp_path, [_finding(coverage="partial")])["coverage"] == "partial"


def test_a_good_store_and_complete_findings_is_complete_with_no_limitations(
    tmp_path: Path,
) -> None:
    _store(tmp_path)
    meta = _meta(tmp_path, [_finding()])
    assert meta["coverage"] == "complete" and meta["limitations"] == []


def test_the_limitations_are_bounded(tmp_path: Path) -> None:
    scans = _store(tmp_path)
    for i in range(120):
        (scans / f"t{i:03d}" / "latest").mkdir(parents=True)
    meta = _meta(tmp_path, [_finding()])
    assert len(meta["limitations"]) <= 51
    assert meta["limitations"][-1].startswith("... and ") and "more" in meta["limitations"][-1]


# -- repos.csv and targets.csv agree --------------------------------------------------------------------------


def test_repos_and_targets_agree_for_a_webapp_whose_latest_attempt_scanned_nothing(
    tmp_path: Path,
) -> None:
    scans = _store(tmp_path)
    _attempt(scans, "web", "2026-10-20-not-scanned", meta=NOT_SCANNED)
    proc, out = _run(tmp_path, [_finding()])
    assert proc.returncode == 0, proc.stderr
    repos = {r["name"]: r["coverage"] for r in _read(out / "repos.csv")}
    targets = {r["name"]: r["coverage"] for r in _read(out / "targets.csv")}
    assert repos == {"web": "partial"} and targets == {"web": "partial"}


def test_repos_and_targets_agree_when_the_latest_attempt_is_unreadable(tmp_path: Path) -> None:
    scans = _store(tmp_path)
    _attempt(scans, "web", "2026-10-20", meta="{ not json")
    proc, out = _run(tmp_path, [_finding()])
    assert proc.returncode == 0, proc.stderr
    assert {r["coverage"] for r in _read(out / "repos.csv")} == {"unknown"}
    assert {r["coverage"] for r in _read(out / "targets.csv")} == {"unknown"}


def test_repos_and_targets_keep_their_findings_coverage_when_the_attempt_is_good(
    tmp_path: Path,
) -> None:
    _store(tmp_path)
    proc, out = _run(tmp_path, [_finding(coverage="partial")])
    assert {r["coverage"] for r in _read(out / "repos.csv")} == {"partial"}
    assert {r["coverage"] for r in _read(out / "targets.csv")} == {"partial"}


def test_a_name_with_no_attempt_in_the_store_keeps_its_findings_coverage(tmp_path: Path) -> None:
    _store(tmp_path)  # the store knows `web`; the finding is for a repo it never scanned
    proc, out = _run(tmp_path, [_finding(repo="elsewhere", target_name="elsewhere")])
    assert {r["name"]: r["coverage"] for r in _read(out / "repos.csv")} == {"elsewhere": "complete"}


def test_build_functions_take_the_attempt_coverage_per_name() -> None:
    findings = [_finding()]
    repos = export_dataset.build_repos_csv(findings, {}, {"web": "partial"})
    targets = export_dataset.build_targets_csv(findings, {}, [], {"web": "partial"})
    assert repos[0]["coverage"] == targets[0]["coverage"] == "partial"
    # and without an attempt map they behave as before
    assert export_dataset.build_repos_csv(findings, {})[0]["coverage"] == "complete"


def test_the_dashboard_doc_states_how_the_scan_store_is_read() -> None:
    doc = (
        REPO_ROOT / "canonical" / "skills" / "security" / "modes" / "dashboard" / "examples.md"
    ).read_text(encoding="utf-8")
    flat = " ".join(doc.split())
    assert "only directories named `{date}` or `{date}-not-scanned` are attempts" in flat
    assert "unrecognised scan directory <target>/<name>" in flat
    assert "never `complete` and never ignored" in flat
    assert "an error (exit 1, nothing written)" in flat
    assert "an absent or empty default store is `coverage: unknown`" in flat
    assert "so they agree" in flat
