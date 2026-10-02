"""Profile layer (migration 159): a switchable operating-context identity, independent of
the active project. Mirrors test_clients_engine.py's shape for the sibling client layer."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Fully-bootstrapped Dream Studio SQLite (migration 159 applied), as a path."""
    target = tmp_path / "studio.db"
    bootstrap_database(target)
    return target


@pytest.fixture
def patched_paths(db_path: Path, tmp_path: Path):
    """Patch `interfaces.cli.ds.resolve_installed_runtime_paths` so the lazy-imported
    `_require_db` in core.profiles.mutations sees `db_path` (same pattern as
    tests/unit/test_extracted_handler_functions.py)."""
    fake = MagicMock()
    fake.sqlite_path = db_path
    fake.source_root = REPO_ROOT
    fake.dream_studio_home = tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake):
        yield fake


def _seed_profile(
    db_path: Path,
    *,
    profile_id: str,
    client_id: str = "seayinsights",
    name: str = "P",
    status: str = "active",
    updated_at: str = "2026-10-02T00:00:00+00:00",
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_profiles"
        " (profile_id, client_id, name, status, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (profile_id, client_id, name, status, updated_at, updated_at),
    )
    conn.commit()
    conn.close()


# ── migration ────────────────────────────────────────────────────────────────


def test_migration_creates_table_with_no_seed_rows(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(business_profiles)")}
        assert {
            "profile_id",
            "client_id",
            "name",
            "claude_config_dir",
            "mcp_client_name",
            "status",
            "created_at",
            "updated_at",
        } <= cols
        count = conn.execute("SELECT COUNT(*) FROM business_profiles").fetchone()[0]
        assert count == 0, "business_profiles must not be seeded (unlike business_clients)"
    finally:
        conn.close()


# ── create_profile ───────────────────────────────────────────────────────────


def test_create_profile_with_valid_client_succeeds(patched_paths, tmp_path: Path):
    from core.profiles.mutations import create_profile

    result = create_profile(
        name="Fulcrum",
        client_id="fulcrum",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True
    assert result["client_id"] == "fulcrum"
    assert result["name"] == "Fulcrum"
    assert result["status"] == "active"
    assert "profile_id" in result


def test_create_profile_with_invalid_client_refuses(patched_paths, tmp_path: Path):
    from core.profiles.mutations import create_profile

    result = create_profile(
        name="Nope",
        client_id="nonexistent-client",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is False
    assert "nonexistent-client" in result["error"]
    # The valid set (seeded by migration 155) is named in the refusal.
    assert "seayinsights" in result["error"]
    assert "fulcrum" in result["error"]
    assert "hypershift" in result["error"]


def test_create_profile_stores_optional_fields(patched_paths, db_path: Path, tmp_path: Path):
    from core.profiles.mutations import create_profile
    from core.profiles.queries import get_profile

    result = create_profile(
        name="Fulcrum",
        client_id="fulcrum",
        claude_config_dir="/home/op/.claude-fulcrum",
        mcp_client_name="fulcrum-mcp",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    stored = get_profile(result["profile_id"], db_path=db_path)
    assert stored["claude_config_dir"] == "/home/op/.claude-fulcrum"
    assert stored["mcp_client_name"] == "fulcrum-mcp"


def test_create_profile_emits_event(monkeypatch, patched_paths, tmp_path: Path):
    import spool.writer as sw
    from core.profiles import mutations

    captured = []
    monkeypatch.setattr(sw, "write_event", lambda d: captured.append(d))

    result = mutations.create_profile(
        name="Fulcrum", client_id="fulcrum", source_root=REPO_ROOT, dream_studio_home=tmp_path
    )
    assert len(captured) == 1
    ev = captured[0]
    assert ev["event_type"] == "profile.created"
    assert ev["payload"] == {
        "profile_id": result["profile_id"],
        "client_id": "fulcrum",
        "name": "Fulcrum",
    }
    assert ev["trace"]["domain"] == "sdlc"
    assert ev["trace"]["attribution_status"] == "fully_attributed"


# ── switch_active_profile ────────────────────────────────────────────────────


def test_switch_active_profile_displaces_previous(patched_paths, db_path: Path, tmp_path: Path):
    from core.profiles.mutations import create_profile, switch_active_profile

    first = create_profile(
        name="SeayInsights",
        client_id="seayinsights",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    second = create_profile(
        name="Fulcrum", client_id="fulcrum", source_root=REPO_ROOT, dream_studio_home=tmp_path
    )

    result = switch_active_profile(
        profile_id=second["profile_id"], source_root=REPO_ROOT, dream_studio_home=tmp_path
    )
    assert result == {"ok": True, "profile_id": second["profile_id"], "status": "active"}

    conn = sqlite3.connect(str(db_path))
    try:
        statuses = dict(conn.execute("SELECT profile_id, status FROM business_profiles").fetchall())
    finally:
        conn.close()
    assert statuses[first["profile_id"]] == "paused"
    assert statuses[second["profile_id"]] == "active"


def test_switch_active_profile_unknown_returns_error(patched_paths, tmp_path: Path):
    from core.profiles.mutations import switch_active_profile

    result = switch_active_profile(
        profile_id="nope", source_root=REPO_ROOT, dream_studio_home=tmp_path
    )
    assert result == {"ok": False, "error": "Profile not found: nope"}


def test_switch_active_profile_emits_events(monkeypatch, patched_paths, tmp_path: Path):
    import spool.writer as sw
    from core.profiles import mutations

    first = mutations.create_profile(
        name="SeayInsights",
        client_id="seayinsights",
        source_root=REPO_ROOT,
        dream_studio_home=tmp_path,
    )
    second = mutations.create_profile(
        name="Fulcrum", client_id="fulcrum", source_root=REPO_ROOT, dream_studio_home=tmp_path
    )

    captured = []
    monkeypatch.setattr(sw, "write_event", lambda d: captured.append(d))
    mutations.switch_active_profile(
        profile_id=second["profile_id"], source_root=REPO_ROOT, dream_studio_home=tmp_path
    )

    event_types = [e["event_type"] for e in captured]
    # Both profiles were 'active' at creation time (create_profile does not displace),
    # so switching to the second displaces BOTH -- same characteristic
    # set_active_project already has.
    assert event_types.count("profile.deactivated") == 2
    deactivated_ids = {
        e["payload"]["profile_id"] for e in captured if e["event_type"] == "profile.deactivated"
    }
    assert deactivated_ids == {first["profile_id"], second["profile_id"]}
    assert event_types[-1] == "profile.activated"
    assert captured[-1]["payload"] == {"profile_id": second["profile_id"]}


# ── queries ───────────────────────────────────────────────────────────────────


def test_active_profile_returns_none_when_no_profile_exists(db_path: Path):
    from core.profiles.queries import active_profile

    assert active_profile(db_path=db_path) is None


def test_active_profile_returns_the_active_row(db_path: Path):
    from core.profiles.queries import active_profile

    _seed_profile(db_path, profile_id="p1", status="paused", updated_at="2026-10-01T00:00:00+00:00")
    _seed_profile(db_path, profile_id="p2", status="active", updated_at="2026-10-02T00:00:00+00:00")
    result = active_profile(db_path=db_path)
    assert result is not None
    assert result["profile_id"] == "p2"


def test_get_profile_unknown_returns_none(db_path: Path):
    from core.profiles.queries import get_profile

    assert get_profile("nonexistent", db_path=db_path) is None


def test_list_profiles_ordering_and_shape(db_path: Path):
    from core.profiles.queries import list_profiles

    _seed_profile(db_path, profile_id="p-old", name="Old", updated_at="2026-10-01T00:00:00+00:00")
    _seed_profile(db_path, profile_id="p-new", name="New", updated_at="2026-10-02T00:00:00+00:00")
    result = list_profiles(db_path=db_path)
    assert [p["profile_id"] for p in result] == ["p-new", "p-old"]
    assert result[0]["name"] == "New"
    assert result[0]["client_id"] == "seayinsights"


def test_list_profiles_excludes_archived_by_default(db_path: Path):
    from core.profiles.queries import list_profiles

    _seed_profile(db_path, profile_id="p-active", status="active")
    _seed_profile(db_path, profile_id="p-archived", status="archived")
    result = list_profiles(db_path=db_path)
    assert [p["profile_id"] for p in result] == ["p-active"]
    result_all = list_profiles(include_archived=True, db_path=db_path)
    assert {p["profile_id"] for p in result_all} == {"p-active", "p-archived"}
