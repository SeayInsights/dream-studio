"""WO-FILESDB-C2: DB-first review-verdict persistence (`_persist_review_verdict`).

Fast unit coverage of the helper that replaced the three inline
``review-verdict.json`` disk writes in verify.py — stores the verdict in the
authority (``business_work_order_artifacts``, kind=``review_verdict``) and only
falls back to a ``.planning`` disk file when the artifact table is absent.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.work_orders.artifacts import get_wo_artifact
from core.work_orders.verify import _persist_review_verdict

REPO_ROOT = Path(__file__).resolve().parents[2]
_MIG_DIR = REPO_ROOT / "core" / "event_store" / "migrations"
_MIG_144 = _MIG_DIR / "144_wo_artifacts.sql"
_MIG_152 = _MIG_DIR / "152_wo_artifacts_instance_key.sql"


def _db_with_table(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_MIG_144.read_text(encoding="utf-8"))
    conn.executescript(_MIG_152.read_text(encoding="utf-8"))
    conn.close()
    return db


def test_verdict_stored_in_authority_no_disk(tmp_path):
    db = _db_with_table(tmp_path)
    planning = tmp_path / "planning"
    verdict = {"work_order_id": "wo-v", "passed": True}

    path = _persist_review_verdict("wo-v", verdict, planning_root=planning, db_path=db)

    # DB-first: stored in the authority, returns None (no disk path), no file on disk.
    assert path is None
    assert list(planning.rglob("review-verdict.json")) == []
    stored = get_wo_artifact("wo-v", "review_verdict", db_path=db)
    assert stored is not None
    assert json.loads(stored)["passed"] is True


def test_verdict_falls_back_to_disk_when_table_absent(tmp_path):
    db = tmp_path / "empty.db"
    sqlite3.connect(str(db)).close()  # no artifact table
    planning = tmp_path / "planning"

    path = _persist_review_verdict("wo-v", {"passed": False}, planning_root=planning, db_path=db)

    # Table absent → disk fallback (returns the written path).
    assert path is not None
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8"))["passed"] is False
