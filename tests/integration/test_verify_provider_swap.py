"""WO-GRADER-PROVIDER-NEUTRAL task 5 (gap 59ba367a): the FULL WO-verify path runs against
a swapped-in stub provider (DS_GRADER_STUB) and produces a scored verdict with the same
JSON shape and the same composite-score arithmetic as the vendor path
(completion*0.5 + correctness*0.3 + quality*0.2) — no vendor CLI required. This is the
behavioral proof that the verification plane is portable, exercised through the public
entry point ``verify_work_order`` rather than an internal helper.
"""

from __future__ import annotations

import json

from tests.helpers.stored_verdict import read_stored_verdict
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.artifact_envelope import unwrap

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-01-01T00:00:00.000000Z"

# Distinct per-role scores so the composite is a real weighted sum, not a passthrough of
# 1.0: 0.8*0.5 + 0.6*0.3 + 0.4*0.2 = 0.40 + 0.18 + 0.08 = 0.66.
_STUB = """import sys, json
sys.stdin.read()  # prompt is delivered on stdin
print(json.dumps({
    "completion_score": 0.8,
    "correctness_score": 0.6,
    "quality_score": 0.4,
    "summary": "stub provider verdict",
    "gaps": [],
}))
"""
_EXPECTED_COMPOSITE = round(0.8 * 0.5 + 0.6 * 0.3 + 0.4 * 0.2, 4)


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


@contextmanager
def _patch_db(db_path: Path):
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        yield


def _seed(db_path: Path, *, work_order_id: str) -> None:
    project_id, milestone_id = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, "Test", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO business_milestones"
        " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description,"
        "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,'in_progress',1,?,?,?)",
        (work_order_id, project_id, milestone_id, "Test WO", "desc", "cleanup", NOW, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,'complete',?,?)",
        (str(uuid.uuid4()), work_order_id, project_id, "T1", "do it", NOW, NOW),
    )
    conn.commit()
    conn.close()


def test_full_verify_path_scores_via_stub_provider(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path)
    work_order_id = str(uuid.uuid4())
    _seed(db_path, work_order_id=work_order_id)

    stub = tmp_path / "stub_grader.py"
    stub.write_text(_STUB, encoding="utf-8")
    monkeypatch.delenv("DREAM_STUDIO_VERIFY_MOCK", raising=False)  # real spawn, not mock mode
    monkeypatch.delenv("DS_GRADER_ARGV", raising=False)
    monkeypatch.setenv("DS_GRADER_STUB", str(stub))

    planning_root = tmp_path / "planning"
    with _patch_db(db_path):
        with patch(
            "core.work_orders.verify_git._collect_git_commits",
            return_value="diff --git a/fake.py b/fake.py\n+# change",
        ):
            from core.work_orders.verify import verify_work_order

            result = verify_work_order(
                work_order_id=work_order_id,
                source_root=REPO_ROOT,
                dream_studio_home=tmp_path,
                planning_root=planning_root,
            )

    # Same JSON shape as the vendor path: per-role grader dicts + the scores block.
    assert result["ok"] is True
    for role in ("completion", "correctness", "quality"):
        assert isinstance(result[role], dict), f"{role} verdict must be present"
    scores = result["scores"]
    assert set(scores) >= {
        "completion_score",
        "correctness_score",
        "quality_score",
        "composite_score",
    }
    # Same composite-score arithmetic as the Claude path, computed from the stub's verdict.
    assert scores["completion_score"] == 0.8
    assert scores["correctness_score"] == 0.6
    assert scores["quality_score"] == 0.4
    assert scores["composite_score"] == _EXPECTED_COMPOSITE == 0.66

    # The verdict was persisted (the same artifact the vendor path writes). Read
    # DB-or-disk, as the independent_review gate does: the zero-disk migration moved
    # verdicts into business_work_order_artifacts, and the disk fallback fires only when
    # the authority write fails -- so asserting is_file() on a healthy authority asserted
    # that persistence had FAILED.
    stored_verdict = read_stored_verdict(
        work_order_id, db_path=db_path, planning_root=planning_root
    )
    assert stored_verdict["scores"]["composite_score"] == 0.66
