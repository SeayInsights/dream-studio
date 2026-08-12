"""WO-ENFORCE-TIERS: graduated enforcement tiers (off / observe / warn / enforce).

The tier ladder lets a team run in observe mode, see exactly what WOULD have been blocked,
then escalate — so the substrate is adoptable by teams that did not build it. Tests cover
tier resolution, the observe-mode report query, and the actual hook decision at each tier.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from runtime.lib import enforcement

REPO_ROOT = Path(__file__).resolve().parents[2]
_NOW = "2026-01-01T00:00:00.000000Z"


# ── tier resolution ─────────────────────────────────────────────────────────────


def test_resolve_tier_default_is_enforce(monkeypatch):
    monkeypatch.delenv("DS_ENFORCE", raising=False)
    monkeypatch.delenv("DS_ENFORCE_TIER", raising=False)
    assert enforcement.resolve_tier() == "enforce"


def test_resolve_tier_reads_env(monkeypatch):
    monkeypatch.delenv("DS_ENFORCE", raising=False)
    for tier in ("off", "observe", "warn", "enforce"):
        monkeypatch.setenv("DS_ENFORCE_TIER", tier)
        assert enforcement.resolve_tier() == tier


def test_resolve_tier_invalid_defaults_to_enforce(monkeypatch):
    monkeypatch.delenv("DS_ENFORCE", raising=False)
    monkeypatch.setenv("DS_ENFORCE_TIER", "loud")
    assert enforcement.resolve_tier() == "enforce"


def test_ds_enforce_zero_is_equivalent_to_off(monkeypatch):
    monkeypatch.setenv("DS_ENFORCE", "0")
    monkeypatch.setenv("DS_ENFORCE_TIER", "enforce")  # DS_ENFORCE=0 must still win
    assert enforcement.resolve_tier() == "off"
    assert enforcement.enforcement_disabled() is True


# ── observe-mode report ─────────────────────────────────────────────────────────


def _scratch_db() -> Path:
    d = Path(tempfile.mkdtemp(prefix="ds-tiers-"))
    db = d / "state" / "studio.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db)
    return db


def _insert_observation_event(db: Path, *, rule: str, reason: str, when: str = _NOW) -> None:
    """Insert a HOOK_EXECUTION_LOGGED canonical event exactly as the ingestor materializes it
    from an observe-mode record (the report reads ai_canonical_events)."""
    conn = sqlite3.connect(str(db))
    payload = {
        "hook_name": "on_edit_enforce",
        "hook_type": "PreToolUse",
        "trigger_context": {
            "decision": "observe",
            "tier": "observe",
            "rule": rule,
            "would_deny_reason": reason,
        },
    }
    conn.execute(
        "INSERT INTO ai_canonical_events (event_id, event_type, event_timestamp, payload)"
        " VALUES (?,?,?,?)",
        (str(uuid.uuid4()), "system.hook.execution.logged", when, json.dumps(payload)),
    )
    conn.commit()
    conn.close()


def test_observations_report_groups_by_rule():
    db = _scratch_db()
    _insert_observation_event(db, rule="authority_source_edit", reason="run ds work-order start A")
    _insert_observation_event(db, rule="authority_source_edit", reason="run ds work-order start B")
    _insert_observation_event(db, rule="zero_disk_planning", reason="use ds files write")

    report = enforcement.observations_report(db_path=db)
    assert report["total"] == 3
    assert report["by_rule"]["authority_source_edit"]["count"] == 2
    assert report["by_rule"]["zero_disk_planning"]["count"] == 1
    sample = report["by_rule"]["authority_source_edit"]["samples"][0]
    assert "ds work-order start" in sample["reason"]


def test_observations_report_ignores_non_observe_events():
    db = _scratch_db()
    conn = sqlite3.connect(str(db))
    payload = {"hook_name": "on_edit_enforce", "trigger_context": {"decision": "allow"}}
    conn.execute(
        "INSERT INTO ai_canonical_events (event_id, event_type, event_timestamp, payload)"
        " VALUES (?,?,?,?)",
        (str(uuid.uuid4()), "system.hook.execution.logged", _NOW, json.dumps(payload)),
    )
    conn.commit()
    conn.close()
    report = enforcement.observations_report(db_path=db)
    assert report["total"] == 0


# ── hook decision at each tier (real subprocess, scratch home) ────────────────────


def _run_edit_hook(
    tier: str, home: Path, project_dir: Path, src: Path
) -> subprocess.CompletedProcess:
    payload = json.dumps(
        {"session_id": "tiers-test", "tool_name": "Edit", "tool_input": {"file_path": str(src)}}
    )
    hook = REPO_ROOT / "runtime" / "hooks" / "meta" / "on-edit-enforce.py"
    env = dict(os.environ)
    env["USERPROFILE"] = str(home)
    env["HOME"] = str(home)
    env["TMP"] = str(home)
    env["TEMP"] = str(home)
    env["DS_ENFORCE_TIER"] = tier
    env.pop("DS_ENFORCE", None)
    return subprocess.run(
        [sys.executable, str(hook)],
        input=payload,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def _scratch_project():
    root = Path(tempfile.mkdtemp(prefix="ds-tiers-hook-"))
    home = root / "home"
    state = home / ".dream-studio" / "state"
    state.mkdir(parents=True, exist_ok=True)
    db = state / "studio.db"
    bootstrap_database(db)
    project_dir = root / "project"
    (project_dir / "src").mkdir(parents=True, exist_ok=True)
    project_id, milestone_id = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, project_path,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (project_id, "p", "", "active", str(project_dir), _NOW, _NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones (milestone_id, project_id, title, status, order_index,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (milestone_id, project_id, "M1", "active", 1, _NOW, _NOW),
    )
    # A created (not in_progress) WO so the would-be-deny names the `ds work-order start` command.
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id, title,"
        " description, work_order_type, status, sequence_order, created_at, updated_at,"
        " last_updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            str(uuid.uuid4()),
            project_id,
            milestone_id,
            "Do the thing",
            "d",
            "cleanup",
            "created",
            1,
            _NOW,
            _NOW,
            _NOW,
        ),
    )
    conn.commit()
    conn.close()
    src = project_dir / "src" / "app.py"
    src.write_text("# source\n", encoding="utf-8")
    return home, project_dir, src


def test_enforce_tier_denies_the_edit():
    home, project_dir, src = _scratch_project()
    proc = _run_edit_hook("enforce", home, project_dir, src)
    data = json.loads(proc.stdout.strip())
    assert data["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_observe_tier_allows_the_edit():
    home, project_dir, src = _scratch_project()
    proc = _run_edit_hook("observe", home, project_dir, src)
    # No deny payload — the edit is allowed (the would-be deny is recorded, not blocked).
    assert proc.stdout.strip() == "" or "deny" not in proc.stdout


def test_warn_tier_allows_but_surfaces_message():
    home, project_dir, src = _scratch_project()
    proc = _run_edit_hook("warn", home, project_dir, src)
    assert "deny" not in proc.stdout  # allowed, not blocked
    assert "work-order start" in proc.stderr  # the message is surfaced on stderr
