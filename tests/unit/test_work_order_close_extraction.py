"""Direct-call tests for the A2.2 split of `_work_order_close` into three
functions in `core.work_orders.close`:

- `run_gate_check` — single-gate predicate
- `check_close_gates` — pure preview (no mutation, no spool)
- `close_work_order` — composer (mutation + spool + next-step hint)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-20T00:00:00+00:00"
PROJECT_ID = "p-close-ext-0001"
WO_DOCS = "wo-docs-no-gates-close-extraction-01"
WO_UI = "wo-ui-with-gates-close-extraction-02"
WO_API = "wo-api-with-gates-close-extraction-03"
MILESTONE_ID = "ms-close-ext-0001"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute(
            "INSERT INTO business_projects VALUES (?, ?, ?, ?, ?, ?)",
            (PROJECT_ID, "Close Extraction Project", "", "active", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, description, status, order_index,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, '', 'pending', 0, ?, ?)",
            (MILESTONE_ID, PROJECT_ID, "First", NOW, NOW),
        )
        # No-gates WO so close happens cleanly without seeding artifacts.
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '', 'in_progress', 'documentation', ?, ?)",
            (WO_DOCS, PROJECT_ID, MILESTONE_ID, "Docs WO", NOW, NOW),
        )
        # Gated WOs so failure/force paths are exercised.
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, ?, '', 'in_progress', 'ui_component', ?, ?)",
            (WO_UI, PROJECT_ID, "UI WO", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, ?, '', 'in_progress', 'api_endpoint', ?, ?)",
            (WO_API, PROJECT_ID, "API WO", NOW, NOW),
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


def _insert_locked_brief(db_path: Path, project_id: str = PROJECT_ID) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_design_briefs"
            " (brief_id, project_id, status, created_at, updated_at)"
            " VALUES (?, ?, 'locked', ?, ?)",
            (f"brief-{project_id}", project_id, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()


def _read_spool_events(spool_root: Path) -> list[dict]:
    events_dir = spool_root / "spool"
    if not events_dir.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in events_dir.glob("*.json")]


# ── run_gate_check ────────────────────────────────────────────────────────────


def test_run_gate_check_returns_pass_for_none_gate(tmp_path: Path) -> None:
    from core.work_orders.close import run_gate_check

    passed, reason = run_gate_check(
        None,
        planning_root=tmp_path,
        work_order_id="any",
        project_id="any",
        conn=None,
    )
    assert passed is True
    assert reason == ""


def test_run_gate_check_design_brief_locked_passes_when_brief_exists(
    db_path: Path, tmp_path: Path
) -> None:
    from core.work_orders.close import run_gate_check

    _insert_locked_brief(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        passed, reason = run_gate_check(
            "design_brief_locked",
            planning_root=tmp_path,
            work_order_id=WO_UI,
            project_id=PROJECT_ID,
            conn=conn,
        )
    assert passed is True
    assert reason == ""


def test_run_gate_check_design_brief_locked_fails_when_missing(
    db_path: Path, tmp_path: Path
) -> None:
    from core.work_orders.close import run_gate_check

    with sqlite3.connect(str(db_path)) as conn:
        passed, reason = run_gate_check(
            "design_brief_locked",
            planning_root=tmp_path,
            work_order_id=WO_UI,
            project_id=PROJECT_ID,
            conn=conn,
        )
    assert passed is False
    assert "design_brief_locked" in reason


def test_run_gate_check_design_critique_passes_with_high_score(tmp_path: Path) -> None:
    from core.work_orders.close import run_gate_check

    wo_dir = tmp_path / "work-orders" / WO_UI
    wo_dir.mkdir(parents=True)
    (wo_dir / "design-critique.md").write_text("Score: 4/5\nLooks good.", encoding="utf-8")

    passed, reason = run_gate_check(
        "design_critique",
        planning_root=tmp_path,
        work_order_id=WO_UI,
        project_id=PROJECT_ID,
        conn=None,
    )
    assert passed is True
    assert reason == ""


def test_run_gate_check_design_critique_fails_below_minimum(tmp_path: Path) -> None:
    from core.work_orders.close import run_gate_check

    wo_dir = tmp_path / "work-orders" / WO_UI
    wo_dir.mkdir(parents=True)
    (wo_dir / "design-critique.md").write_text("Score: 2/5\nNeeds work.", encoding="utf-8")

    passed, reason = run_gate_check(
        "design_critique",
        planning_root=tmp_path,
        work_order_id=WO_UI,
        project_id=PROJECT_ID,
        conn=None,
    )
    assert passed is False
    assert "score 2 is below minimum 3" in reason


def test_run_gate_check_security_scan_fails_when_blocked(tmp_path: Path) -> None:
    from core.work_orders.close import run_gate_check

    wo_dir = tmp_path / "work-orders" / WO_API
    wo_dir.mkdir(parents=True)
    (wo_dir / "security-scan.md").write_text("BLOCKED — critical issue found", encoding="utf-8")

    passed, reason = run_gate_check(
        "security_scan",
        planning_root=tmp_path,
        work_order_id=WO_API,
        project_id=PROJECT_ID,
        conn=None,
    )
    assert passed is False
    assert "BLOCKED" in reason


# ── check_close_gates ─────────────────────────────────────────────────────────


def test_check_close_gates_returns_error_for_unknown_wo(patched_paths, tmp_path: Path) -> None:
    from core.work_orders.close import check_close_gates

    result = check_close_gates(
        work_order_id="does-not-exist",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is False
    assert "not found" in result["error"]


def test_check_close_gates_passes_when_no_gates_configured(patched_paths, tmp_path: Path) -> None:
    from core.work_orders.close import check_close_gates

    result = check_close_gates(
        work_order_id=WO_DOCS,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert result["gates_pass"] is True
    assert result["gate_failures"] == []
    assert result["work_order_id"] == WO_DOCS
    assert result["type_id"] == "documentation"


def test_check_close_gates_reports_failures_for_gated_wo(patched_paths, tmp_path: Path) -> None:
    from core.work_orders.close import check_close_gates

    result = check_close_gates(
        work_order_id=WO_UI,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert result["gates_pass"] is False
    assert any("design_brief_locked" in f for f in result["gate_failures"])


def test_check_close_gates_does_not_mutate_status(
    patched_paths, db_path: Path, tmp_path: Path
) -> None:
    from core.work_orders.close import check_close_gates

    check_close_gates(
        work_order_id=WO_DOCS,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    with sqlite3.connect(str(db_path)) as conn:
        status = conn.execute(
            "SELECT status FROM business_work_orders WHERE work_order_id = ?", (WO_DOCS,)
        ).fetchone()[0]
    assert status == "in_progress"


# ── close_work_order ──────────────────────────────────────────────────────────


def test_close_work_order_returns_error_for_unknown_wo(
    patched_paths, tmp_path: Path, spool_root: Path
) -> None:
    from core.work_orders.close import close_work_order

    result = close_work_order(
        work_order_id="does-not-exist",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is False
    assert "not found" in result["error"]


def test_close_work_order_blocks_when_gate_fails_without_force(
    patched_paths, tmp_path: Path, spool_root: Path
) -> None:
    from core.work_orders.close import close_work_order

    result = close_work_order(
        work_order_id=WO_UI,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is False
    assert result["error"] == "Gate check failed"
    assert any("design_brief_locked" in f for f in result["failures"])


def test_close_work_order_succeeds_when_no_gates_configured(
    patched_paths, db_path: Path, tmp_path: Path, spool_root: Path
) -> None:
    from core.work_orders.close import close_work_order

    result = close_work_order(
        work_order_id=WO_DOCS,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert result["status"] == "closed"
    assert result["forced"] is False
    assert result["bypassed_gates"] == []


def test_close_work_order_emits_work_order_closed_event(
    patched_paths, tmp_path: Path, spool_root: Path
) -> None:
    from core.work_orders.close import close_work_order

    close_work_order(
        work_order_id=WO_DOCS,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    events = _read_spool_events(spool_root)
    assert any(e["event_type"] == "work_order.closed" for e in events)


def test_close_work_order_force_overrides_gate_failures(
    patched_paths, db_path: Path, tmp_path: Path, spool_root: Path
) -> None:
    from core.work_orders.close import close_work_order

    result = close_work_order(
        work_order_id=WO_UI,
        force=True,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert result["forced"] is True
    assert result["status"] == "closed"
    assert len(result["bypassed_gates"]) >= 1


def test_close_work_order_force_emits_gate_bypassed_events(
    patched_paths, tmp_path: Path, spool_root: Path
) -> None:
    from core.work_orders.close import close_work_order

    close_work_order(
        work_order_id=WO_UI,
        force=True,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    events = _read_spool_events(spool_root)
    bypassed = [e for e in events if e["event_type"] == "gate.bypassed"]
    assert len(bypassed) >= 1


def test_close_work_order_surfaces_next_wo_in_milestone(
    patched_paths, db_path: Path, tmp_path: Path, spool_root: Path
) -> None:
    from core.work_orders.close import close_work_order

    # Seed a second open WO in the same milestone — it should surface as next.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, status,"
        " work_order_type, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, '', 'created', 'documentation', ?, ?)",
        ("wo-next-in-ms", PROJECT_ID, MILESTONE_ID, "Next WO", NOW, NOW),
    )
    conn.commit()
    conn.close()

    result = close_work_order(
        work_order_id=WO_DOCS,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert result["next_work_order"]["work_order_id"] == "wo-next-in-ms"
    assert result["next_command"] == "ds work-order start wo-next-in-ms"


def test_close_work_order_surfaces_milestone_complete_when_last_in_milestone(
    patched_paths, tmp_path: Path, spool_root: Path
) -> None:
    from core.work_orders.close import close_work_order

    result = close_work_order(
        work_order_id=WO_DOCS,
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True
    assert result.get("milestone_complete") is True
    assert result.get("milestone_id") == MILESTONE_ID
    assert result["next_command"] == f"ds milestone close {MILESTONE_ID}"
