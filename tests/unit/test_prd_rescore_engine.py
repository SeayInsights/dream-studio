"""WO P3 (4d495283) — the PRD+SOW rescore engine (SPEC-0001).

The engine derives a per-capability + overall 0-100 PRD score and per-milestone SOW entries
from existing authority (studio.db) + docstore (files.db) state, and renders the living
document to the docstore. No new studio.db tables. It must be deterministic + idempotent.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from core.files.store import read_file_by_name, write_file
from core.prd.rescore import rescore_prd

_TS = "2026-08-05T00:00:00+00:00"

CAP_MAP = """\
capabilities:
  - capability_id: cap-a
    title: Capability A
    weight: 1.0
  - capability_id: cap-b
    title: Capability B
    weight: 1.0
milestone_capabilities:
  m1: [cap-a]
  m2: [cap-b]
"""


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    studio = tmp_path / "studio.db"
    bootstrap_database(studio)
    conn = sqlite3.connect(str(studio))
    try:
        # m1 complete (delivers cap-a), m2 pending (cap-b not yet delivered).
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id,project_id,title,description,status,order_index,created_at,updated_at)"
            " VALUES ('m1','p','Milestone One','ship the A capability','complete',10,'t','t'),"
            "        ('m2','p','Milestone Two','ship the B capability','pending',20,'t','t')"
        )
        # Two closed WOs under m1 with verify_score composites (0.9, 0.7) -> 90, 70.
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id,project_id,milestone_id,title,status,verify_score,created_at,updated_at)"
            " VALUES ('w1','p','m1','WO one','closed',0.9,'t','t'),"
            "        ('w2','p','m1','WO two','closed',0.7,'t','t')"
        )
        conn.commit()
    finally:
        conn.close()

    files = tmp_path / "files.db"
    write_file("prd/capability-map.yaml", CAP_MAP, "application/yaml", "planning", db_path=files)
    # A milestone gate artifact for m1 → adds a design-audit signal (Score 4/5 = 80).
    write_file(
        "milestones/m1/design-audit.md", "Score: 4/5", "text/markdown", "planning", db_path=files
    )
    return studio, files


def test_rescore_prd_deterministic_and_idempotent(tmp_path: Path):
    studio, files = _seed(tmp_path)

    kw = dict(db_path=studio, files_db_path=files, planning_root=tmp_path / ".planning", now=_TS)
    r1 = rescore_prd("p", **kw)
    r2 = rescore_prd("p", **kw)

    assert r1["ok"] is True
    # Deterministic + idempotent: identical result (timestamp fixed) across runs.
    assert r1 == r2

    # m1 score = mean(90, 70, design 80) = 80.0; delivers cap-a.
    m1 = next(m for m in r1["milestones"] if m["milestone_id"] == "m1")
    assert m1["score"] == 80.0
    assert m1["status"] == "complete"
    assert "Delivered 2 work order(s)" in m1["accomplished"]
    assert m1["set_out_to"] == "ship the A capability"

    # m2 is pending → not delivered; accomplished states in-progress.
    m2 = next(m for m in r1["milestones"] if m["milestone_id"] == "m2")
    assert "in progress" in m2["accomplished"].lower()

    caps = {c["capability_id"]: c for c in r1["capabilities"]}
    assert caps["cap-a"]["status"] == "scored" and caps["cap-a"]["score"] == 80.0
    assert caps["cap-b"]["status"] == "not_delivered" and caps["cap-b"]["score"] == 0.0

    # Overall = weighted mean of capability sub-scores (80, 0) = 40.0; coverage = 1/2.
    assert r1["overall_score"] == 40.0
    assert r1["coverage"] == 0.5

    # The living document is rendered to the docstore (project-scoped) and reflects the scores.
    doc = read_file_by_name("prd/prd-sow.md", project_id="p", db_path=files)["content"]
    if isinstance(doc, (bytes, bytearray)):
        doc = doc.decode("utf-8")
    assert "PRD + Statement of Work" in doc
    assert "Overall PRD score: 40.0/100" in doc
    assert "Statement of Work - Milestones" in doc
    assert "Milestone One" in doc and "Milestone Two" in doc


def test_rescore_prd_missing_capability_map_is_empty_not_error(tmp_path: Path):
    """No capability map yet → engine returns a valid empty-coverage result, never raises."""
    studio = tmp_path / "studio.db"
    bootstrap_database(studio)
    files = tmp_path / "files.db"
    result = rescore_prd(
        "p", db_path=studio, files_db_path=files, planning_root=tmp_path / ".planning", now=_TS
    )
    assert result["ok"] is True
    assert result["capabilities"] == []
    assert result["overall_score"] == 0.0
    assert result["coverage"] == 0.0
