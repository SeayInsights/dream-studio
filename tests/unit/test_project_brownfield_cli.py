"""Brownfield onboarding through the CLI, and the reuse flag that reaches the caller.

WHY THIS FILE EXISTS. `discover_project_candidates`, `bulk_acquire` and
`aggregate_readiness` had no caller under `interfaces/`. The only thing that reached them
was prose in `canonical/skills/ds-project/modes/brownfield/SKILL.md` telling a model to
import and call them itself, so the capability could not be scripted, piped or tested
through the surface every other project operation uses.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from interfaces.cli.ds import main


@pytest.fixture
def home(tmp_path):
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True)
    bootstrap_database(db_path)
    return tmp_path


@pytest.fixture
def candidates(tmp_path):
    """Two directories that look like projects, one python and one node.

    The marker files are load-bearing: discovery recognises a candidate by `.git` or one
    of a fixed list of manifests, so a directory holding only `main.py` is correctly not a
    project, and using one here would silently make this fixture produce a single
    candidate while every count below still read as though it had produced two.
    """
    root = tmp_path / "repos"
    (root / "alpha").mkdir(parents=True)
    (root / "alpha" / "pyproject.toml").write_text('[project]\nname = "alpha"\n', encoding="utf-8")
    (root / "beta").mkdir(parents=True)
    (root / "beta" / "package.json").write_text('{"name": "beta"}\n', encoding="utf-8")
    return root


def _run(argv, capsys) -> tuple[int, dict]:
    rc = main(argv)
    out = capsys.readouterr().out
    # The ingestor writes progress lines to this stream on some runs; the payload is the
    # JSON object, so parse from its first brace rather than assuming it starts the output.
    start = out.index("{")
    return rc, json.loads(out[start:])


# ── discover ─────────────────────────────────────────────────────────────────


def test_discover_finds_candidates_without_registering_any(home, candidates, capsys):
    rc, out = _run(
        ["--home", str(home), "project", "discover", str(candidates), "--no-github"],
        capsys,
    )
    assert rc == 0
    assert out["ok"] is True
    assert {c["name"] for c in out["candidates"]} == {"alpha", "beta"}

    # READ-ONLY IS THE POINT. Discovery that enrolled what it found would be unusable on a
    # machine holding more than one person's work.
    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    try:
        assert conn.execute("SELECT COUNT(*) FROM business_projects").fetchone()[0] == 0
    finally:
        conn.close()


# ── bulk-onboard ─────────────────────────────────────────────────────────────


def test_bulk_onboard_registers_only_the_selected_candidate(home, candidates, tmp_path, capsys):
    _, discovered = _run(
        ["--home", str(home), "project", "discover", str(candidates), "--no-github"],
        capsys,
    )
    listing = tmp_path / "candidates.json"
    listing.write_text(json.dumps(discovered), encoding="utf-8")

    # `--select 2` means the second row as `discover` PRINTED it, 1-based. Treating it as
    # an index would register the wrong project, which is not a failure anyone would see.
    second = discovered["candidates"][1]["name"]
    rc, out = _run(
        ["--home", str(home), "project", "bulk-onboard", str(listing), "--select", "2"],
        capsys,
    )
    assert rc == 0
    assert out["counts"]["registered"] == 1
    assert out["registered"][0]["project_name"] == second

    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM business_projects")]
    finally:
        conn.close()
    assert names == [second]


def test_a_second_run_reports_the_project_as_skipped_not_registered(
    home, candidates, tmp_path, capsys
):
    """The count an operator re-running this would act on.

    `bulk_acquire` branched on `result.get("idempotent")`, a key nothing in the codebase
    writes, so its `skipped` list could never be non-empty and every re-run reported each
    already-registered project as freshly registered. The data was never wrong -- intake
    reuses the row -- but the report was, and this command exists to be re-run as an
    operator adds repos.
    """
    _, discovered = _run(
        ["--home", str(home), "project", "discover", str(candidates), "--no-github"],
        capsys,
    )
    listing = tmp_path / "candidates.json"
    listing.write_text(json.dumps(discovered), encoding="utf-8")
    argv = ["--home", str(home), "project", "bulk-onboard", str(listing)]

    _, first = _run(argv, capsys)
    assert first["counts"]["registered"] == 2
    assert first["counts"]["skipped"] == 0

    _, second = _run(argv, capsys)
    assert second["counts"]["registered"] == 0
    assert second["counts"]["skipped"] == 2

    # And no duplicate row was minted either way.
    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    try:
        assert conn.execute("SELECT COUNT(*) FROM business_projects").fetchone()[0] == 2
    finally:
        conn.close()


def test_a_selection_outside_the_listing_is_refused_by_number(home, candidates, tmp_path, capsys):
    _, discovered = _run(
        ["--home", str(home), "project", "discover", str(candidates), "--no-github"],
        capsys,
    )
    listing = tmp_path / "candidates.json"
    listing.write_text(json.dumps(discovered), encoding="utf-8")

    rc, out = _run(
        ["--home", str(home), "project", "bulk-onboard", str(listing), "--select", "9"],
        capsys,
    )
    assert rc == 1
    assert out["ok"] is False
    # The refusal names the number and the range, because "invalid selection" leaves the
    # operator re-reading a list to work out which of their numbers was wrong.
    assert "9" in out["error"] and "1..2" in out["error"]


# ── readiness ────────────────────────────────────────────────────────────────


def test_readiness_reports_zero_findings_rather_than_claiming_clean(
    home, candidates, tmp_path, capsys
):
    """No audits run is a different statement from no findings found.

    `aggregate_readiness` only reads what previous audits persisted, so it reports a
    count. A project nobody audited and a project audited clean both read zero here, and
    the command prints the count instead of a verdict so the two are not conflated.
    """
    _, discovered = _run(
        ["--home", str(home), "project", "discover", str(candidates), "--no-github"],
        capsys,
    )
    listing = tmp_path / "candidates.json"
    listing.write_text(json.dumps(discovered), encoding="utf-8")
    _, registered = _run(
        ["--home", str(home), "project", "bulk-onboard", str(listing), "--select", "1"],
        capsys,
    )
    project_id = registered["registered"][0]["project_id"]

    rc, out = _run(["--home", str(home), "project", "readiness", project_id], capsys)
    assert rc == 0
    assert out["readiness_report"]["finding_count"] == 0
    assert out["stabilization_scope"] == []
    assert "ok" in out
