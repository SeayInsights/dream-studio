"""TA3: Universal token capture via PostToolUse hook."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

# ── shared fixture data ────────────────────────────────────────────────────────

PROJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MILESTONE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
WO_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
TASK_A = "11111111-1111-1111-1111-111111111111"
NOW = "2026-05-22T00:00:00+00:00"
ORPHAN_PROJECT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


@pytest.fixture
def db_home(tmp_path):
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True)
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects VALUES (?, 'Test Project', 'desc', 'active', ?, ?)",
            (PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, 'M1', 'active', ?, ?)",
            (MILESTONE_ID, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, 'WO1', NULL, 'in_progress', 'documentation', ?, ?)",
            (WO_ID, PROJECT_ID, MILESTONE_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, 'Task A', 'desc A', 'pending', ?, ?)",
            (TASK_A, WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return tmp_path


def _spool_events(spool_root: Path) -> list[dict]:
    spool_dir = spool_root / "spool"
    if not spool_dir.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(spool_dir.glob("*.json"))]


def _events_of_type(spool_root: Path, event_type: str) -> list[dict]:
    return [e for e in _spool_events(spool_root) if e.get("event_type") == event_type]


def _make_payload(
    tool_name: str = "Read",
    tool_use_id: str = "toolu_01",
    session_id: str = "sess_01",
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_creation: int = 0,
    cache_read: int = 0,
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tool_use_id": tool_use_id,
        "session_id": session_id,
        "model": model,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_creation,
            "cache_read_input_tokens": cache_read,
        },
    }


def _diag_entries(diag_dir: Path, source_prefix: str = "") -> list[dict]:
    entries = []
    for f in diag_dir.glob("*.jsonl"):
        if source_prefix and source_prefix not in f.stem:
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
    return entries


# ── token_capture unit tests ───────────────────────────────────────────────────


def test_handle_post_tool_use_emits_fully_attributed_when_active_task_set(
    db_home, tmp_path, monkeypatch
):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(db_home / "state" / "active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))

    from core.sdlc.active_task import set_active_task

    set_active_task(TASK_A)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload())

    events = _events_of_type(tmp_path / "spool-root", "token.consumed")
    assert len(events) == 1
    trace = events[0]["trace"]
    assert trace["attribution_status"] == "fully_attributed"
    assert trace["task_id"] == TASK_A
    assert trace["work_order_id"] == WO_ID
    assert trace["milestone_id"] == MILESTONE_ID
    assert trace["project_id"] == PROJECT_ID
    assert trace["tool_name"] == "Read"
    assert trace["tool_use_id"] == "toolu_01"
    payload = events[0]["payload"]
    assert payload["input_tokens"] == 100
    assert payload["output_tokens"] == 50
    assert payload["granularity"] == "tool_invocation"


def test_handle_post_tool_use_emits_partial_when_json_marker_resolves(
    db_home, tmp_path, monkeypatch
):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))

    marker = tmp_path / ".dream-studio-project"
    marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": PROJECT_ID,
                "project_name": "Test Project",
                "created_at": NOW,
                "metadata": {"git_remote_url": None, "registered_from_path": "/irrelevant"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload())

    events = _events_of_type(tmp_path / "spool-root", "token.consumed")
    assert len(events) == 1
    trace = events[0]["trace"]
    assert trace["attribution_status"] == "partial"
    assert trace["project_id"] == PROJECT_ID
    assert trace["task_id"] is None
    payload = events[0]["payload"]
    assert payload.get("project_name") == "Test Project"


def test_handle_post_tool_use_emits_partial_from_plain_uuid_marker(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))

    marker = tmp_path / ".dream-studio-project"
    marker.write_text(PROJECT_ID + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload())

    events = _events_of_type(tmp_path / "spool-root", "token.consumed")
    assert len(events) == 1
    trace = events[0]["trace"]
    assert trace["attribution_status"] == "partial"
    assert trace["project_id"] == PROJECT_ID
    # project_name must NOT appear in payload for plain-UUID markers
    assert "project_name" not in events[0]["payload"]


def test_handle_post_tool_use_partial_when_marker_project_not_in_db(db_home, tmp_path, monkeypatch):
    """Q3 decision: marker resolves, project not in DB → partial + anomaly logged."""
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    diag_dir = tmp_path / "diag"
    diag_dir.mkdir()
    monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(diag_dir))

    marker = tmp_path / ".dream-studio-project"
    marker.write_text(ORPHAN_PROJECT_ID + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload())

    events = _events_of_type(tmp_path / "spool-root", "token.consumed")
    assert len(events) == 1
    assert events[0]["trace"]["attribution_status"] == "partial"
    assert events[0]["trace"]["project_id"] == ORPHAN_PROJECT_ID

    # Anomaly should have been logged.
    entries = _diag_entries(diag_dir)
    anomalies = [e for e in entries if e.get("category") == "anomaly"]
    assert any("not found in business_projects" in str(e.get("details", {})) for e in anomalies)


def test_handle_post_tool_use_emits_orphan_when_nothing_resolves(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    monkeypatch.chdir(tmp_path)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload())

    events = _events_of_type(tmp_path / "spool-root", "token.consumed")
    assert len(events) == 1
    trace = events[0]["trace"]
    assert trace["attribution_status"] == "orphan"
    assert trace["project_id"] is None
    assert trace["task_id"] is None


def test_handle_post_tool_use_skips_emission_when_no_usage(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    diag_dir = tmp_path / "diag"
    diag_dir.mkdir()
    monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(diag_dir))

    payload = {"tool_name": "Read", "tool_use_id": "toolu_01"}

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(payload)

    assert len(_events_of_type(tmp_path / "spool-root", "token.consumed")) == 0
    entries = _diag_entries(diag_dir)
    assert any("no usage block" in str(e.get("details", {})) for e in entries)


def test_handle_post_tool_use_skips_emission_when_all_zero_usage(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    diag_dir = tmp_path / "diag"
    diag_dir.mkdir()
    monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(diag_dir))

    payload = _make_payload(input_tokens=0, output_tokens=0)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(payload)

    assert len(_events_of_type(tmp_path / "spool-root", "token.consumed")) == 0
    entries = _diag_entries(diag_dir)
    assert any("all-zero" in str(e.get("details", {})) for e in entries)


def test_handle_post_tool_use_logs_performance_when_slow(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    diag_dir = tmp_path / "diag"
    diag_dir.mkdir()
    monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(diag_dir))
    monkeypatch.chdir(tmp_path)

    # Monkeypatch write_envelopes to sleep > 50ms to trigger performance log.
    import emitters.shared.spool_writer as _sw

    original = _sw.write_envelopes

    def slow_write(envelopes, root=None):
        time.sleep(0.06)
        original(envelopes, root)

    monkeypatch.setattr(_sw, "write_envelopes", slow_write)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload())

    entries = _diag_entries(diag_dir)
    perf = [e for e in entries if e.get("category") == "performance"]
    assert len(perf) > 0


def test_handle_post_tool_use_captures_git_context(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    monkeypatch.chdir(tmp_path)

    fake_commit = "abc1234def5678abc1234def5678abc1234def56"
    fake_branch = "feat/ta3-token-capture-hook"

    import core.telemetry.token_capture as _tc

    def fake_run(cmd, **kwargs):
        if "rev-parse" in cmd and "HEAD" in cmd and "--abbrev-ref" not in cmd:
            r = mock.MagicMock()
            r.returncode = 0
            r.stdout = fake_commit
            return r
        if "--abbrev-ref" in cmd:
            r = mock.MagicMock()
            r.returncode = 0
            r.stdout = fake_branch
            return r
        r = mock.MagicMock()
        r.returncode = 1
        r.stdout = ""
        return r

    monkeypatch.setattr(subprocess, "run", fake_run)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload())

    events = _events_of_type(tmp_path / "spool-root", "token.consumed")
    assert len(events) == 1
    exec_ctx = events[0]["payload"].get("execution_context", {})
    assert exec_ctx.get("git_commit") == fake_commit
    assert exec_ctx.get("git_branch") == fake_branch


def test_handle_post_tool_use_no_absolute_paths_in_event(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))

    marker = tmp_path / ".dream-studio-project"
    marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": PROJECT_ID,
                "project_name": "Test",
                "created_at": NOW,
                "metadata": {"git_remote_url": None, "registered_from_path": "/should/not/appear"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload())

    events = _events_of_type(tmp_path / "spool-root", "token.consumed")
    assert len(events) == 1
    event_str = json.dumps(events[0])
    # registered_from_path must not appear in the emitted event
    assert "registered_from_path" not in event_str
    assert "/should/not/appear" not in event_str


def test_handle_post_tool_use_never_raises(tmp_path, monkeypatch):
    """Resilience: even with every step throwing, the function must not raise."""
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))

    import core.telemetry.token_capture as _tc

    monkeypatch.setattr(
        _tc, "_extract_usage", lambda p: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    from core.telemetry.token_capture import handle_post_tool_use

    # Must not raise.
    handle_post_tool_use(_make_payload())


def test_handle_post_tool_use_cache_tokens_preserved(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    monkeypatch.chdir(tmp_path)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload(cache_creation=200, cache_read=150))

    events = _events_of_type(tmp_path / "spool-root", "token.consumed")
    assert len(events) == 1
    p = events[0]["payload"]
    assert p["cache_creation_input_tokens"] == 200
    assert p["cache_read_input_tokens"] == 150


# ── machine_id unit tests ──────────────────────────────────────────────────────


def test_get_machine_id_generates_and_persists(tmp_path, monkeypatch):
    id_file = tmp_path / "machine_id"
    monkeypatch.setenv("DS_MACHINE_ID_PATH", str(id_file))

    from core.telemetry.machine_id import _reset_cache, get_machine_id

    _reset_cache()

    mid = get_machine_id()
    assert mid
    assert id_file.exists()
    assert id_file.read_text(encoding="utf-8").strip() == mid


def test_get_machine_id_returns_same_value_on_subsequent_calls(tmp_path, monkeypatch):
    id_file = tmp_path / "machine_id"
    monkeypatch.setenv("DS_MACHINE_ID_PATH", str(id_file))

    from core.telemetry.machine_id import _reset_cache, get_machine_id

    _reset_cache()

    first = get_machine_id()
    second = get_machine_id()
    assert first == second


def test_get_machine_id_reads_existing_file(tmp_path, monkeypatch):
    id_file = tmp_path / "machine_id"
    fixed_id = "deadbeef-0000-0000-0000-000000000000"
    id_file.write_text(fixed_id, encoding="utf-8")
    monkeypatch.setenv("DS_MACHINE_ID_PATH", str(id_file))

    from core.telemetry.machine_id import _reset_cache, get_machine_id

    _reset_cache()

    assert get_machine_id() == fixed_id


def test_get_machine_id_env_override_honored(tmp_path, monkeypatch):
    custom_path = tmp_path / "custom_dir" / "machine_id"
    monkeypatch.setenv("DS_MACHINE_ID_PATH", str(custom_path))

    from core.telemetry.machine_id import _reset_cache, get_machine_id

    _reset_cache()

    mid = get_machine_id()
    assert custom_path.exists()
    assert custom_path.read_text(encoding="utf-8").strip() == mid


# ── cwd_resolver unit tests ────────────────────────────────────────────────────


def test_resolve_project_from_cwd_json_marker(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    marker = tmp_path / ".dream-studio-project"
    marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": PROJECT_ID,
                "project_name": "Test Project",
                "created_at": NOW,
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from core.sdlc.cwd_resolver import resolve_project_from_cwd

    ctx = resolve_project_from_cwd()

    assert ctx is not None
    assert ctx.project_id == PROJECT_ID
    assert ctx.project_name == "Test Project"
    assert ctx.marker_format == "json"


def test_resolve_project_from_cwd_plain_uuid_marker(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    marker = tmp_path / ".dream-studio-project"
    marker.write_text(PROJECT_ID + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from core.sdlc.cwd_resolver import resolve_project_from_cwd

    ctx = resolve_project_from_cwd()

    assert ctx is not None
    assert ctx.project_id == PROJECT_ID
    assert ctx.project_name is None
    assert ctx.marker_format == "plain_uuid"


def test_resolve_project_from_cwd_walks_up_parents(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    # Marker in parent, cwd is a subdirectory.
    (tmp_path / ".dream-studio-project").write_text(PROJECT_ID + "\n", encoding="utf-8")
    subdir = tmp_path / "src" / "components"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)

    from core.sdlc.cwd_resolver import resolve_project_from_cwd

    ctx = resolve_project_from_cwd()

    assert ctx is not None
    assert ctx.project_id == PROJECT_ID


def test_resolve_project_from_cwd_returns_none_when_no_marker(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from core.sdlc.cwd_resolver import resolve_project_from_cwd

    ctx = resolve_project_from_cwd()

    assert ctx is None


def test_resolve_project_from_cwd_logs_anomaly_for_malformed_marker(tmp_path, monkeypatch):
    diag_dir = tmp_path / "diag"
    diag_dir.mkdir()
    monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(diag_dir))
    marker = tmp_path / ".dream-studio-project"
    marker.write_text("this is not a uuid or json {{{{", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from core.sdlc.cwd_resolver import resolve_project_from_cwd

    ctx = resolve_project_from_cwd()

    assert ctx is None
    entries = _diag_entries(diag_dir)
    assert any(e.get("category") == "anomaly" for e in entries)


def test_resolve_project_from_cwd_logs_anomaly_when_project_not_in_db(
    db_home, tmp_path, monkeypatch
):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    diag_dir = tmp_path / "diag"
    diag_dir.mkdir()
    monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(diag_dir))
    marker = tmp_path / ".dream-studio-project"
    marker.write_text(ORPHAN_PROJECT_ID + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from core.sdlc.cwd_resolver import resolve_project_from_cwd

    ctx = resolve_project_from_cwd()

    # Returns context anyway (Q3 decision).
    assert ctx is not None
    assert ctx.project_id == ORPHAN_PROJECT_ID
    entries = _diag_entries(diag_dir)
    assert any(e.get("category") == "anomaly" for e in entries)


def test_resolve_project_from_cwd_stops_at_git_boundary(tmp_path, monkeypatch):
    """Walk stops at .git/ — marker above the git root is not found."""
    # Marker at the outer level (above the git repo root).
    (tmp_path / ".dream-studio-project").write_text(PROJECT_ID + "\n", encoding="utf-8")
    # Git repo inside tmp_path.
    gitrepo = tmp_path / "gitrepo"
    (gitrepo / ".git").mkdir(parents=True)
    # cwd is inside the git repo.
    src = gitrepo / "src"
    src.mkdir()
    monkeypatch.chdir(src)

    from core.sdlc.cwd_resolver import resolve_project_from_cwd

    ctx = resolve_project_from_cwd()

    # .git boundary at gitrepo/ stops the walk — marker above it is not found.
    assert ctx is None


def test_resolve_project_from_cwd_stops_before_home(tmp_path, monkeypatch):
    """Marker at the home directory level is not found — home is exclusive upper bound."""
    # Treat tmp_path as the fake home; place a marker there.
    (tmp_path / ".dream-studio-project").write_text(PROJECT_ID + "\n", encoding="utf-8")
    # cwd is a grandchild of "home".
    child = tmp_path / "projects" / "myrepo"
    child.mkdir(parents=True)
    monkeypatch.chdir(child)
    # Remove the test cap so only the home boundary governs this walk.
    monkeypatch.delenv("DS_CWD_RESOLVER_ROOT", raising=False)
    # Mock _get_home to return tmp_path as the home directory.
    import core.sdlc.cwd_resolver as _resolver

    monkeypatch.setattr(_resolver, "_get_home", lambda: tmp_path.resolve())

    from core.sdlc.cwd_resolver import resolve_project_from_cwd

    ctx = resolve_project_from_cwd()

    # Home boundary fires when parent == home; marker at home level is not visited.
    assert ctx is None


# ── diagnostics unit tests ─────────────────────────────────────────────────────


def test_log_diagnostic_writes_entry_with_expected_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(tmp_path))

    from core.telemetry.diagnostics import log_diagnostic

    log_diagnostic(
        category="anomaly",
        source="token_capture.handle_post_tool_use",
        context={"tool_name": "Read"},
        details={"error_message": "test"},
        session_id="sess_01",
    )

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    entry = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert entry["category"] == "anomaly"
    assert entry["source"] == "token_capture.handle_post_tool_use"
    assert entry["context"]["tool_name"] == "Read"
    assert "ts" in entry


def test_log_diagnostic_uses_source_prefix_filename(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(tmp_path))

    from core.telemetry.diagnostics import log_diagnostic

    log_diagnostic(category="failure", source="cwd_resolver._parse_marker")

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    assert files[0].name == "cwd-resolver.jsonl"


def test_log_diagnostic_never_raises_when_dir_unwritable(tmp_path, monkeypatch):
    # Point to a file path (not a dir) so mkdir fails.
    fake = tmp_path / "not_a_dir.txt"
    fake.write_text("x", encoding="utf-8")
    monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(fake / "subdir"))

    from core.telemetry.diagnostics import log_diagnostic

    # Must not raise.
    log_diagnostic(category="anomaly", source="test.source", details={"msg": "ok"})


def test_log_diagnostic_env_override_honored(tmp_path, monkeypatch):
    custom_dir = tmp_path / "custom_diag"
    custom_dir.mkdir()
    monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(custom_dir))

    from core.telemetry.diagnostics import log_diagnostic

    log_diagnostic(category="performance", source="token_capture.spool", duration_ms=123.4)

    files = list(custom_dir.glob("*.jsonl"))
    assert len(files) == 1


# ── hook shim unit tests ───────────────────────────────────────────────────────


def _get_hook_shim_path() -> Path:
    return (
        Path(__file__).resolve().parents[2] / "runtime" / "hooks" / "core" / "on-post-tool-use.py"
    )


def _run_shim(stdin_data: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(_get_hook_shim_path())],
        input=stdin_data,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def test_shim_exits_0_on_success(tmp_path, monkeypatch):
    """Shim must always exit 0, even with a full payload."""
    payload = json.dumps(_make_payload())
    result = _run_shim(
        payload,
        extra_env={
            "DS_ACTIVE_TASK_PATH": str(tmp_path / "no_task.json"),
            "DS_SPOOL_ROOT": str(tmp_path / "spool"),
            "DS_DIAGNOSTICS_DIR": str(tmp_path / "diag"),
            "DS_MACHINE_ID_PATH": str(tmp_path / "machine_id"),
        },
    )
    assert result.returncode == 0


def test_shim_exits_0_when_malformed_json(tmp_path):
    result = _run_shim(
        "this is not json",
        extra_env={
            "DS_ACTIVE_TASK_PATH": str(tmp_path / "no_task.json"),
            "DS_SPOOL_ROOT": str(tmp_path / "spool"),
            "DS_DIAGNOSTICS_DIR": str(tmp_path / "diag"),
            "DS_MACHINE_ID_PATH": str(tmp_path / "machine_id"),
        },
    )
    assert result.returncode == 0


def test_shim_exits_0_when_module_raises(tmp_path, monkeypatch):
    """Shim catches exceptions from token_capture and still exits 0."""
    # Provide a broken payload that will cause issues inside handle_post_tool_use.
    payload = json.dumps({"tool_name": "Read", "usage": {"input_tokens": -999}})
    result = _run_shim(
        payload,
        extra_env={
            "DS_ACTIVE_TASK_PATH": str(tmp_path / "no_task.json"),
            "DS_SPOOL_ROOT": str(tmp_path / "spool"),
            "DS_DIAGNOSTICS_DIR": str(tmp_path / "diag"),
            "DS_MACHINE_ID_PATH": str(tmp_path / "machine_id"),
        },
    )
    assert result.returncode == 0


def test_shim_writes_hook_failures_jsonl_on_import_error(tmp_path):
    """When token_capture can't be imported, shim writes to hook-failures.jsonl."""
    diag_dir = tmp_path / "diag"
    diag_dir.mkdir()

    # Build a fake plugin root whose core.telemetry.token_capture raises on import.
    # Setting CLAUDE_PLUGIN_ROOT causes the shim to insert this dir at sys.path[0]
    # so the broken module is found before the real one.
    fake_root = tmp_path / "fake_plugin_root"
    tc_dir = fake_root / "core" / "telemetry"
    tc_dir.mkdir(parents=True)
    (tc_dir.parent.parent / "__init__.py").write_text("", encoding="utf-8")
    (tc_dir.parent / "__init__.py").write_text("", encoding="utf-8")
    (tc_dir / "__init__.py").write_text("", encoding="utf-8")
    (tc_dir / "token_capture.py").write_text(
        "raise ImportError('deliberate import failure')", encoding="utf-8"
    )

    import os

    env = os.environ.copy()
    env["DS_DIAGNOSTICS_DIR"] = str(diag_dir)
    env["DS_MACHINE_ID_PATH"] = str(tmp_path / "machine_id")
    env["DS_ACTIVE_TASK_PATH"] = str(tmp_path / "no_task.json")
    env["DS_SPOOL_ROOT"] = str(tmp_path / "spool")
    # CLAUDE_PLUGIN_ROOT makes _get_plugin_root() return fake_root, which the
    # shim inserts at sys.path[0] — so the broken token_capture is found first.
    env["CLAUDE_PLUGIN_ROOT"] = str(fake_root)

    result = subprocess.run(
        [sys.executable, str(_get_hook_shim_path())],
        input=json.dumps(_make_payload()),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    hook_fail_path = diag_dir / "hook-failures.jsonl"
    assert hook_fail_path.exists()
    entry = json.loads(hook_fail_path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert entry["category"] == "failure"


# ── ds project register --path unit tests ─────────────────────────────────────


def test_project_register_cli_writes_marker_to_path(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(db_home))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(tmp_path / "diag"))

    project_dir = tmp_path / "my_project"
    project_dir.mkdir()

    import io
    from contextlib import redirect_stdout

    from interfaces.cli.ds import main

    buf = io.StringIO()
    with redirect_stdout(buf):
        exit_code = main(
            ["project", "register", "--name", "My Project", "--path", str(project_dir)]
        )

    assert exit_code == 0
    marker_path = project_dir / ".dream-studio-project"
    assert marker_path.exists()
    data = json.loads(marker_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert "project_id" in data
    assert data["project_name"] == "My Project"
    assert "created_at" in data


def test_project_register_cli_requires_path(db_home, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))

    # Argparse should refuse to parse without --path.
    with pytest.raises(SystemExit) as exc_info:
        from interfaces.cli.ds import main

        main(["project", "register", "--name", "No Path Project"])
    assert exc_info.value.code != 0


def test_project_register_api_without_path_logs_warning(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    diag_dir = tmp_path / "diag"
    diag_dir.mkdir()
    monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(diag_dir))

    from core.projects.mutations import register_project

    result = register_project(
        name="Programmatic Project",
        project_path=None,
        source_root=db_home,
        dream_studio_home=db_home,
    )

    assert result["ok"] is True
    assert result["marker_written"] is False
    entries = _diag_entries(diag_dir)
    assert any("marker not created" in str(e.get("details", {})) for e in entries)


def test_project_register_api_with_path_writes_marker(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))

    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    from core.projects.mutations import register_project

    result = register_project(
        name="API Project",
        project_path=project_dir,
        source_root=db_home,
        dream_studio_home=db_home,
    )

    assert result["ok"] is True
    assert result["marker_written"] is True
    marker_path = project_dir / ".dream-studio-project"
    assert marker_path.exists()
    data = json.loads(marker_path.read_text(encoding="utf-8"))
    assert data["project_id"] == result["project_id"]


# ── integration tests ──────────────────────────────────────────────────────────


def test_integration_full_payload_produces_canonical_event(db_home, tmp_path, monkeypatch):
    """Complete PostToolUse payload → token.consumed in canonical_events."""
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    monkeypatch.chdir(tmp_path)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload(input_tokens=300, output_tokens=150))

    # Ingest the spool into canonical_events.
    from spool.ingestor import ingest_pending

    ingest_pending(root=tmp_path / "spool-root", db_path=db_home / "state" / "studio.db")

    conn = sqlite3.connect(str(db_home / "state" / "studio.db"))
    try:
        row = conn.execute(
            "SELECT event_type, trace, payload FROM canonical_events WHERE event_type = ?",
            ("token.consumed",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    trace = json.loads(row[1])
    payload = json.loads(row[2])
    assert trace["domain"] == "telemetry"
    assert trace["attribution_status"] == "orphan"
    assert payload["input_tokens"] == 300
    assert payload["output_tokens"] == 150
    assert payload["granularity"] == "tool_invocation"


def test_integration_set_active_task_then_hook_produces_fully_attributed(
    db_home, tmp_path, monkeypatch
):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(db_home / "state" / "active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))

    from core.sdlc.active_task import set_active_task

    set_active_task(TASK_A)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload())

    from spool.ingestor import ingest_pending

    ingest_pending(root=tmp_path / "spool-root", db_path=db_home / "state" / "studio.db")

    conn = sqlite3.connect(str(db_home / "state" / "studio.db"))
    try:
        row = conn.execute(
            "SELECT trace FROM canonical_events WHERE event_type = ?",
            ("token.consumed",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    trace = json.loads(row[0])
    assert trace["attribution_status"] == "fully_attributed"
    assert trace["task_id"] == TASK_A
    assert trace["project_id"] == PROJECT_ID


def test_integration_no_task_json_marker_produces_partial(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))

    marker = tmp_path / ".dream-studio-project"
    marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": PROJECT_ID,
                "project_name": "Test Project",
                "created_at": NOW,
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload())

    from spool.ingestor import ingest_pending

    ingest_pending(root=tmp_path / "spool-root", db_path=db_home / "state" / "studio.db")

    conn = sqlite3.connect(str(db_home / "state" / "studio.db"))
    try:
        row = conn.execute(
            "SELECT trace, payload FROM canonical_events WHERE event_type = ?",
            ("token.consumed",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    trace = json.loads(row[0])
    payload = json.loads(row[1])
    assert trace["attribution_status"] == "partial"
    assert trace["project_id"] == PROJECT_ID
    assert payload.get("project_name") == "Test Project"


def test_integration_no_task_no_marker_produces_orphan(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    monkeypatch.chdir(tmp_path)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload())

    from spool.ingestor import ingest_pending

    ingest_pending(root=tmp_path / "spool-root", db_path=db_home / "state" / "studio.db")

    conn = sqlite3.connect(str(db_home / "state" / "studio.db"))
    try:
        row = conn.execute(
            "SELECT trace FROM canonical_events WHERE event_type = ?",
            ("token.consumed",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    trace = json.loads(row[0])
    assert trace["attribution_status"] == "orphan"
    assert trace["project_id"] is None


def test_integration_marker_orphan_project_produces_partial_with_anomaly(
    db_home, tmp_path, monkeypatch
):
    """Q3: marker with unknown project_id → partial + anomaly logged."""
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    diag_dir = tmp_path / "diag"
    diag_dir.mkdir()
    monkeypatch.setenv("DS_DIAGNOSTICS_DIR", str(diag_dir))

    marker = tmp_path / ".dream-studio-project"
    marker.write_text(ORPHAN_PROJECT_ID + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from core.telemetry.token_capture import handle_post_tool_use

    handle_post_tool_use(_make_payload())

    events = _events_of_type(tmp_path / "spool-root", "token.consumed")
    assert len(events) == 1
    assert events[0]["trace"]["attribution_status"] == "partial"
    assert events[0]["trace"]["project_id"] == ORPHAN_PROJECT_ID

    entries = _diag_entries(diag_dir)
    assert any(e.get("category") == "anomaly" for e in entries)
