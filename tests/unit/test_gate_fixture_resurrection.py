"""Tests for core/gates/test_fixture_resurrection_guard.py.

Covers the synthetic-diff failure path and the dead-table ledger logic.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import core.gates.test_fixture_resurrection_guard as guard

# ---------------------------------------------------------------------------
# build_dead_table_ledger
# ---------------------------------------------------------------------------


def test_ledger_returns_frozenset() -> None:
    result = guard.build_dead_table_ledger()
    assert isinstance(result, frozenset)


def test_ledger_nonempty_against_real_migrations() -> None:
    dead = guard.build_dead_table_ledger()
    assert len(dead) > 0, "expected at least one dead table from real migration dir"


def test_known_dead_table_in_ledger() -> None:
    dead = guard.build_dead_table_ledger()
    # prd_tasks was dropped by migration 103 and never recreated.
    assert "prd_tasks" in dead


def test_known_live_table_absent_from_ledger() -> None:
    dead = guard.build_dead_table_ledger()
    # raw_approaches is alive — still referenced by vw_approach_patterns.
    assert "raw_approaches" not in dead


def test_synthetic_migrations_create_then_drop(tmp_path: Path) -> None:
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "001_create.sql").write_text(
        "CREATE TABLE zombie_table (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    (mig_dir / "002_drop.sql").write_text("DROP TABLE zombie_table;", encoding="utf-8")
    with patch.object(guard, "MIGRATIONS_DIR", mig_dir):
        dead = guard.build_dead_table_ledger()
    assert "zombie_table" in dead


def test_synthetic_migrations_drop_then_recreate_is_alive(tmp_path: Path) -> None:
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "001_create.sql").write_text(
        "CREATE TABLE revived (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    (mig_dir / "002_drop.sql").write_text("DROP TABLE revived;", encoding="utf-8")
    (mig_dir / "003_recreate.sql").write_text(
        "CREATE TABLE revived (id INTEGER PRIMARY KEY, name TEXT);", encoding="utf-8"
    )
    with patch.object(guard, "MIGRATIONS_DIR", mig_dir):
        dead = guard.build_dead_table_ledger()
    assert "revived" not in dead


def test_rename_target_treated_as_alive(tmp_path: Path) -> None:
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "001_rename.sql").write_text(
        "ALTER TABLE old_name RENAME TO new_name;", encoding="utf-8"
    )
    with patch.object(guard, "MIGRATIONS_DIR", mig_dir):
        dead = guard.build_dead_table_ledger()
    assert "new_name" not in dead


def test_rename_intermediate_suffix_excluded(tmp_path: Path) -> None:
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    # A migration that drops an intermediate table (a _new suffix table).
    # The guard treats _new / _temp / _backup as rename intermediates — skipped.
    (mig_dir / "001_cleanup.sql").write_text(
        "DROP TABLE some_table_new;\nDROP TABLE some_table_temp;\n", encoding="utf-8"
    )
    with patch.object(guard, "MIGRATIONS_DIR", mig_dir):
        dead = guard.build_dead_table_ledger()
    assert "some_table_new" not in dead
    assert "some_table_temp" not in dead


# ---------------------------------------------------------------------------
# Synthetic-diff failure path (the core gate behavior)
# ---------------------------------------------------------------------------


def _make_diff(table: str, if_not_exists: bool = False) -> str:
    clause = "IF NOT EXISTS " if if_not_exists else ""
    # Embed SQL inside a Python string, as it appears in real test fixtures.
    # The guard regex `^\+[^+].*?CREATE TABLE` requires CREATE TABLE to follow
    # at least one non-'+' character after the leading '+' on the diff line.
    return (
        "diff --git a/tests/unit/test_something.py b/tests/unit/test_something.py\n"
        "--- a/tests/unit/test_something.py\n"
        "+++ b/tests/unit/test_something.py\n"
        f'+    conn.execute("CREATE TABLE {clause}{table} (id INTEGER)")\n'
    )


def test_gate_fires_on_dead_table_in_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    dead = guard.build_dead_table_ledger()
    assert dead, "ledger is empty — cannot exercise failure path"
    any_dead = next(iter(dead))

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(guard, "_diff_text", lambda _base_ref: _make_diff(any_dead))
    assert guard.main() == 1


def test_gate_passes_for_live_table_in_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(guard, "_diff_text", lambda _base_ref: _make_diff("business_work_orders"))
    assert guard.main() == 0


def test_gate_passes_for_rename_intermediate_in_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(guard, "_diff_text", lambda _base_ref: _make_diff("some_table_new"))
    assert guard.main() == 0


def test_gate_passes_on_empty_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(guard, "_diff_text", lambda _base_ref: "")
    assert guard.main() == 0


def test_gate_short_circuits_on_github_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dead = guard.build_dead_table_ledger()
    any_dead = next(iter(dead))

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    # Even if the diff contains a dead-table resurrection, the gate exits 0 in CI.
    monkeypatch.setattr(guard, "_diff_text", lambda _base_ref: _make_diff(any_dead))
    assert guard.main() == 0


def test_gate_fires_on_if_not_exists_syntax(monkeypatch: pytest.MonkeyPatch) -> None:
    dead = guard.build_dead_table_ledger()
    any_dead = next(iter(dead))

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(
        guard,
        "_diff_text",
        lambda _base_ref: _make_diff(any_dead, if_not_exists=True),
    )
    assert guard.main() == 1


def test_gate_fires_only_on_added_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    dead = guard.build_dead_table_ledger()
    any_dead = next(iter(dead))

    # Context line (space prefix, not '+') — should NOT trigger the gate.
    diff = (
        "diff --git a/tests/unit/test_foo.py b/tests/unit/test_foo.py\n"
        f'     conn.execute("CREATE TABLE {any_dead} (id INTEGER)")\n'
    )
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(guard, "_diff_text", lambda _base_ref: diff)
    assert guard.main() == 0


# ---------------------------------------------------------------------------
# Explicit named-table coverage: prd_documents (dead) and ds_documents (dead)
# Gate module: core/gates/test_fixture_resurrection_guard.py
# Test file: tests/unit/test_gate_fixture_resurrection.py  (here)
# ---------------------------------------------------------------------------


def test_prd_documents_is_dead_in_ledger() -> None:
    # prd_documents was created in migration 040/047 and dropped in migration 103
    # (103_drop_prd_cluster.sql — same migration that dropped prd_tasks).
    dead = guard.build_dead_table_ledger()
    assert "prd_documents" in dead


def test_ds_documents_is_dead_in_ledger() -> None:
    # ds_documents was created in migration 007 and dropped in migration 127
    # (127_drop_ds_documents_from_studio_db.sql — three-store architecture fix:
    # ds_documents now lives in files.db, not studio.db).
    dead = guard.build_dead_table_ledger()
    assert "ds_documents" in dead


def test_gate_fires_on_prd_documents_in_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(guard, "_diff_text", lambda _base_ref: _make_diff("prd_documents"))
    assert guard.main() == 1


def test_gate_fires_for_ds_documents_in_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    # ds_documents is now dead in studio.db (moved to files.db in migration 127).
    # A test diff that re-declares the dropped table in studio.db would resurrect
    # a dead table — the gate must block it.  (The migration-127 drop is what makes
    # ds_documents dead in the ledger; recreating it studio-side is the violation.)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(guard, "_diff_text", lambda _base_ref: _make_diff("ds_documents"))
    assert guard.main() == 1


# ---------------------------------------------------------------------------
# WO-GATE-SQL-PARSERS: DDL keywords inside comments must not trip the gate
# ---------------------------------------------------------------------------


def test_gate_ignores_dead_table_ddl_in_python_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A CREATE TABLE for a dead table inside a `#` comment is prose, not real
    DDL, and must NOT trip the guard (WO-GATE-SQL-PARSERS)."""
    dead = guard.build_dead_table_ledger()
    any_dead = next(iter(dead))
    diff = (
        "diff --git a/tests/unit/test_x.py b/tests/unit/test_x.py\n"
        "--- a/tests/unit/test_x.py\n"
        "+++ b/tests/unit/test_x.py\n"
        f"+    # historical note: we used to CREATE TABLE {any_dead} (id INTEGER)\n"
    )
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(guard, "_diff_text", lambda _base_ref: diff)
    assert guard.main() == 0, "DDL inside a # comment must not trip the guard"


def test_gate_still_fires_on_real_ddl_alongside_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control: real DDL on its own line still fires even when a comment
    with DDL is also present."""
    dead = guard.build_dead_table_ledger()
    any_dead = next(iter(dead))
    diff = (
        "diff --git a/tests/unit/test_x.py b/tests/unit/test_x.py\n"
        "--- a/tests/unit/test_x.py\n"
        "+++ b/tests/unit/test_x.py\n"
        "+    # CREATE TABLE ignore_me (id)\n"
        f'+    conn.execute("CREATE TABLE {any_dead} (id INTEGER)")\n'
    )
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(guard, "_diff_text", lambda _base_ref: diff)
    assert guard.main() == 1, "real DDL must still fire"


def test_ledger_ignores_ddl_in_sql_comments(tmp_path: Path) -> None:
    """Commented CREATE TABLE lines (-- and /* */) must not add junk table names
    (if/is/on/…) to the dead-table ledger; real DDL is still recorded."""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "001_create.sql").write_text(
        "-- CREATE TABLE if_ghost (id);\n"
        "/* planned: CREATE TABLE block_ghost (id); */\n"
        "CREATE TABLE real_zombie (id INTEGER PRIMARY KEY);\n",
        encoding="utf-8",
    )
    (mig_dir / "002_drop.sql").write_text(
        "-- DROP TABLE real_zombie was considered\nDROP TABLE real_zombie;\n",
        encoding="utf-8",
    )
    with patch.object(guard, "MIGRATIONS_DIR", mig_dir):
        dead = guard.build_dead_table_ledger()
    assert "real_zombie" in dead
    assert "if_ghost" not in dead and "block_ghost" not in dead
    assert "if" not in dead and "is" not in dead


def test_strip_sql_comments_helper() -> None:
    from core.gates.sql_comments import strip_sql_comments

    assert "CREATE" not in strip_sql_comments("-- CREATE TABLE if x")
    assert "CREATE" not in strip_sql_comments("# CREATE TABLE if x")
    assert "CREATE" not in strip_sql_comments("/* CREATE TABLE x */")
    # real DDL (including inside a string literal, no comment marker) is preserved
    assert "CREATE TABLE foo" in strip_sql_comments('conn.execute("CREATE TABLE foo")')
