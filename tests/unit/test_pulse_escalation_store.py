"""WO-FILESDB-C4B S3: the pulse open-escalation count reads the authority store.

Before C4B-3 the pulse globbed meta/*.md for "ESC-" + "unresolved". Now it reads
business_work_order_artifacts (kind='escalation', status='unresolved') and migrates
any legacy open disk ESC-*.md file into the store first, so switching the reader never
drops the count. These tests cover the migration, the store-backed scan, and the
defensive disk fallback.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.artifacts import get_wo_artifact
from core.work_orders.escalation import (
    _record_escalation_artifact,
    backfill_open_escalations_from_disk,
    resolve_escalation,
    scan_open_escalation_files,
)

WO = "1a2b3c4d-0000-4000-8000-000000000001"
WO8 = WO[:8]


@pytest.fixture
def db(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    conn.execute(
        "INSERT INTO business_projects (project_id,name,description,status,created_at,updated_at)"
        " VALUES ('p1','P','','active','2026-01-01','2026-01-01')"
    )
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id,project_id,title,description,status,order_index,created_at,updated_at)"
        " VALUES ('m1','p1','M','','active',0,'2026-01-01','2026-01-01')"
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id,project_id,milestone_id,title,description,status,work_order_type,created_at,updated_at)"
        " VALUES (?,'p1','m1','T','','in_progress','infrastructure','2026-01-01','2026-01-01')",
        (WO,),
    )
    conn.commit()
    conn.close()
    return target


def _write_disk_esc(
    meta_dir: Path, name: str, *, resolved: bool = False, reason: str = "cap hit"
) -> Path:
    meta_dir.mkdir(parents=True, exist_ok=True)
    status = "resolved" if resolved else "unresolved"
    path = meta_dir / f"{name}.md"
    path.write_text(f"# {name} — status: {status}\n\nReason: {reason}\n", encoding="utf-8")
    return path


# ── scan_open_escalation_files ───────────────────────────────────────────────


def test_scan_finds_unresolved_ignores_resolved(tmp_path: Path):
    meta = tmp_path / "meta"
    _write_disk_esc(meta, f"ESC-RETRYCAP-{WO8}")
    _write_disk_esc(meta, "ESC-OUTCOME-deadbeef", resolved=True)
    (meta / "not-an-esc.md").write_text("nothing here", encoding="utf-8")

    names = {p.name for p in scan_open_escalation_files(meta)}
    assert names == {f"ESC-RETRYCAP-{WO8}.md"}


def test_scan_missing_dir_is_empty(tmp_path: Path):
    assert scan_open_escalation_files(tmp_path / "nope") == []
    assert scan_open_escalation_files(None) == []


# ── backfill_open_escalations_from_disk ──────────────────────────────────────


def test_backfill_migrates_open_disk_esc_into_store(db: Path, tmp_path: Path):
    meta = tmp_path / "meta"
    _write_disk_esc(meta, f"ESC-RETRYCAP-{WO8}", reason="retry cap reached")

    written = backfill_open_escalations_from_disk(meta, db_path=db)
    assert written == 1

    content = get_wo_artifact(WO, "escalation", instance_key="retrycap", db_path=db)
    assert content is not None
    data = json.loads(content)
    assert data["status"] == "unresolved"
    assert data["type"] == "retrycap"
    assert data["reason"] == "retry cap reached"


def test_backfill_is_idempotent(db: Path, tmp_path: Path):
    meta = tmp_path / "meta"
    _write_disk_esc(meta, f"ESC-OUTCOME-{WO8}")
    assert backfill_open_escalations_from_disk(meta, db_path=db) == 1
    # Second pass: already represented in the store → nothing new written.
    assert backfill_open_escalations_from_disk(meta, db_path=db) == 0


def test_backfill_does_not_reopen_a_resolved_escalation(db: Path, tmp_path: Path):
    meta = tmp_path / "meta"
    _write_disk_esc(meta, f"ESC-RETRYCAP-{WO8}")
    backfill_open_escalations_from_disk(meta, db_path=db)
    resolve_escalation(WO, db_path=db)  # operator resolves it in the store
    # A stale disk file lingering does not resurrect the resolved store record.
    assert backfill_open_escalations_from_disk(meta, db_path=db) == 0
    data = json.loads(get_wo_artifact(WO, "escalation", instance_key="retrycap", db_path=db))
    assert data["status"] == "resolved"


def test_backfill_skips_unknown_wo_prefix(db: Path, tmp_path: Path):
    meta = tmp_path / "meta"
    _write_disk_esc(meta, "ESC-RETRYCAP-ffffffff")  # no WO with this prefix
    assert backfill_open_escalations_from_disk(meta, db_path=db) == 0


# ── pulse check_open_escalations (store-backed) ──────────────────────────────


@pytest.fixture
def pulse(db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point pulse_collector's paths at the fixture DB + a tmp meta dir."""
    import core.config.paths as paths_mod
    import interfaces.cli.pulse_collector as pc

    meta = tmp_path / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths_mod, "meta_dir", lambda: meta)
    monkeypatch.setattr(paths_mod, "state_dir", lambda: db.parent)
    return pc, meta


def test_pulse_reads_open_escalations_from_store(pulse):
    pc, _meta = pulse
    _record_escalation_artifact(
        WO, instance_key="retrycap", reason="x", db_path=pc.paths.state_dir() / "studio.db"
    )
    result = pc.check_open_escalations()
    assert result == [f"ESC-RETRYCAP-{WO8}"]


def test_pulse_migrates_disk_then_counts_from_store(pulse):
    pc, meta = pulse
    _write_disk_esc(meta, f"ESC-OUTCOME-{WO8}")  # legacy disk ESC, not yet in store
    result = pc.check_open_escalations()
    assert result == [f"ESC-OUTCOME-{WO8}"]
    # And it now lives in the store (migrated), not just counted off disk.
    assert get_wo_artifact(
        WO, "escalation", instance_key="outcome", db_path=pc.paths.state_dir() / "studio.db"
    )


def test_pulse_resolved_escalation_drops_out_of_count(pulse):
    pc, _meta = pulse
    db_path = pc.paths.state_dir() / "studio.db"
    _record_escalation_artifact(WO, instance_key="retrycap", reason="x", db_path=db_path)
    assert pc.check_open_escalations() == [f"ESC-RETRYCAP-{WO8}"]
    resolve_escalation(WO, db_path=db_path)
    assert pc.check_open_escalations() == []
