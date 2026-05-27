"""Direct-call tests for the A2.7 split of `_milestone_close` into the
`close_milestone` composer in `core.milestones.close`. The pure function
now returns one canonical result dict across every path — replacing the
legacy mix of plain-text success output and JSON error output."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-20T00:00:00+00:00"
PROJECT_ID = "p-ms-ext-0001"
MILESTONE_ID = "ms-ext-0001"
WO_UI_ID = "wo-ms-ext-ui-01"
WO_API_ID = "wo-ms-ext-api-01"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute(
            "INSERT INTO business_projects VALUES (?, ?, ?, ?, ?, ?)",
            (PROJECT_ID, "MS Ext Project", "", "active", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, description, status, order_index,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, '', 'active', 0, ?, ?)",
            (MILESTONE_ID, PROJECT_ID, "Alpha Release", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '', 'closed', 'ui_component', ?, ?)",
            (WO_UI_ID, PROJECT_ID, MILESTONE_ID, "Build hero", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '', 'closed', 'api_endpoint', ?, ?)",
            (WO_API_ID, PROJECT_ID, MILESTONE_ID, "Auth endpoint", NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return target


@pytest.fixture
def patched_paths(db_path: Path, tmp_path: Path):
    fake = MagicMock()
    fake.sqlite_path = db_path
    fake.source_root = REPO_ROOT
    fake.dream_studio_home = tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake):
        yield fake


@pytest.fixture
def spool_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "spool-root"
    monkeypatch.setenv("DS_SPOOL_ROOT", str(root))
    return root


def _ms_artifact_dir(tmp_path: Path) -> Path:
    return tmp_path / ".planning" / "milestones" / MILESTONE_ID


def _write_all_passing(tmp_path: Path) -> None:
    d = _ms_artifact_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "design-audit.md").write_text("Score: 3/4\nLooks solid.\n", encoding="utf-8")
    (d / "security-audit.md").write_text("All clear.\n", encoding="utf-8")
    (d / "harden-results.md").write_text("PASSED\n", encoding="utf-8")
    (d / "cwv-results.md").write_text("PASSED\n", encoding="utf-8")


def _read_spool_events(spool_root: Path) -> list[dict]:
    events = list(spool_root.rglob("*.json")) if spool_root.exists() else []
    return [json.loads(p.read_text(encoding="utf-8")) for p in events]


# ── error paths ───────────────────────────────────────────────────────────────


def test_close_milestone_returns_error_for_unknown_milestone(
    patched_paths, tmp_path: Path, spool_root: Path
) -> None:
    from core.milestones.close import close_milestone

    result = close_milestone(
        milestone_id="does-not-exist",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is False
    assert "not found" in result["error"]


def test_close_milestone_returns_open_wo_list_when_wos_incomplete(
    patched_paths, db_path: Path, tmp_path: Path, spool_root: Path
) -> None:
    from core.milestones.close import close_milestone

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE business_work_orders SET status = 'in_progress' WHERE work_order_id = ?",
        (WO_UI_ID,),
    )
    conn.commit()
    conn.close()

    result = close_milestone(
        milestone_id=MILESTONE_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is False
    assert result["error"] == "Cannot close milestone: open work orders remain"
    assert any(w["work_order_id"] == WO_UI_ID for w in result["open_work_orders"])


def test_close_milestone_returns_gate_failures_list(
    patched_paths, tmp_path: Path, spool_root: Path
) -> None:
    """No artifacts present → all 4 gate checks fail (UI milestone)."""
    from core.milestones.close import close_milestone

    result = close_milestone(
        milestone_id=MILESTONE_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is False
    assert result["error"] == "Milestone verification failed"
    assert any("Design audit required" in f for f in result["failures"])
    assert any("Security audit required" in f for f in result["failures"])
    assert any("Hardening check required" in f for f in result["failures"])
    assert any("Core Web Vitals" in f for f in result["failures"])


# ── success paths ─────────────────────────────────────────────────────────────


def test_close_milestone_succeeds_when_artifacts_pass(
    patched_paths, db_path: Path, tmp_path: Path, spool_root: Path
) -> None:
    from core.milestones.close import close_milestone

    _write_all_passing(tmp_path)
    result = close_milestone(
        milestone_id=MILESTONE_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert result["milestone_id"] == MILESTONE_ID
    assert result["title"] == "Alpha Release"
    assert result["project_id"] == PROJECT_ID
    assert result["status"] == "complete"
    assert result["forced"] is False
    assert result["bypassed_gates"] == []
    assert "completed_at" in result
    # Phase 18.2.3: close_milestone() is event-sourced. The DB row is updated
    # asynchronously by MilestoneProjection; the return dict is authoritative.


def test_close_milestone_skips_cwv_for_non_ui_milestone(
    patched_paths, db_path: Path, tmp_path: Path, spool_root: Path
) -> None:
    from core.milestones.close import close_milestone

    # Demote the only UI WO so the milestone has no UI surface.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE business_work_orders SET work_order_type = 'api_endpoint' WHERE work_order_id = ?",
        (WO_UI_ID,),
    )
    conn.commit()
    conn.close()

    d = _ms_artifact_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "design-audit.md").write_text("Score: 3/4\n", encoding="utf-8")
    (d / "security-audit.md").write_text("clear\n", encoding="utf-8")
    (d / "harden-results.md").write_text("PASSED\n", encoding="utf-8")
    # No cwv-results.md — should not be required for non-UI milestone.

    result = close_milestone(
        milestone_id=MILESTONE_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True


def test_close_milestone_emits_milestone_completed_event(
    patched_paths, tmp_path: Path, spool_root: Path
) -> None:
    from core.milestones.close import close_milestone

    _write_all_passing(tmp_path)
    close_milestone(
        milestone_id=MILESTONE_ID,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    events = _read_spool_events(spool_root)
    assert any(e["event_type"] == "milestone.completed" for e in events)


# ── force path ────────────────────────────────────────────────────────────────


def test_close_milestone_force_bypasses_failures(
    patched_paths, db_path: Path, tmp_path: Path, spool_root: Path
) -> None:
    from core.milestones.close import close_milestone

    result = close_milestone(
        milestone_id=MILESTONE_ID,
        force=True,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert result["forced"] is True
    assert result["status"] == "complete"
    assert len(result["bypassed_gates"]) >= 1
    # Phase 18.2.3: DB row updated asynchronously by MilestoneProjection.


def test_close_milestone_force_emits_gate_bypassed_events(
    patched_paths, tmp_path: Path, spool_root: Path
) -> None:
    from core.milestones.close import close_milestone

    close_milestone(
        milestone_id=MILESTONE_ID,
        force=True,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    events = _read_spool_events(spool_root)
    bypassed = [e for e in events if e["event_type"] == "gate.bypassed"]
    assert len(bypassed) >= 1
