"""Tests for Phase 19.1 — Unified Extensions Schema (migration 095).

Proving gate:
- Migration applies cleanly on fresh DB
- All 15 columns present with correct types
- CHECK constraints enforced (invalid inserts rejected)
- Decision 6 readiness query returns correct rows on planted fixtures
- No Phase 18 tables modified (purely additive)
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

MIGRATION_SQL = (
    Path(__file__).parents[2]
    / "core"
    / "event_store"
    / "migrations"
    / "095_unified_extensions_schema.sql"
).read_text(encoding="utf-8")


# ── DB fixture ────────────────────────────────────────────────────────────────


@pytest.fixture
def ext_conn():
    """In-memory DB with migration 095 applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(MIGRATION_SQL)
    yield conn
    conn.close()


def _ext_id():
    return str(uuid.uuid4())


def _insert_ext(conn, **kwargs):
    """Insert a ds_user_extensions row with defaults for unspecified columns."""
    defaults = {
        "extension_id": _ext_id(),
        "skill_id": "ds-quality:security",
        "extension_type": "example",
        "content": '{"text": "example content"}',
        "status": "proposed",
        "past_wo_count": 0,
    }
    defaults.update(kwargs)
    cols = ", ".join(defaults)
    placeholders = ", ".join(["?"] * len(defaults))
    conn.execute(
        f"INSERT INTO ds_user_extensions ({cols}) VALUES ({placeholders})",
        list(defaults.values()),
    )
    conn.commit()


# ── Schema structure ──────────────────────────────────────────────────────────


class TestSchemaStructure:
    def test_table_exists_after_migration(self, ext_conn):
        row = ext_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ds_user_extensions'"
        ).fetchone()
        assert row is not None

    def test_all_15_columns_present(self, ext_conn):
        cols = {r[1] for r in ext_conn.execute("PRAGMA table_info(ds_user_extensions)")}
        expected = {
            "extension_id",
            "skill_id",
            "extension_type",
            "content",
            "source_signal",
            "compiled_from",
            "status",
            "created_at",
            "last_validated_at",
            "baseline_eval_score",
            "current_eval_score",
            "past_wo_count",
            "user_confirmed_at",
            "user_confirmed_by",
            "suppressed_reason",
        }
        assert expected == cols, f"Missing: {expected - cols}, Extra: {cols - expected}"

    def test_extension_id_is_primary_key(self, ext_conn):
        pk_cols = [
            r[1] for r in ext_conn.execute("PRAGMA table_info(ds_user_extensions)") if r[5] == 1
        ]
        assert pk_cols == ["extension_id"]

    def test_three_indexes_created(self, ext_conn):
        idx = {
            r[0]
            for r in ext_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='ds_user_extensions'"
            )
            if not r[0].startswith("sqlite_auto")
        }
        assert "idx_extensions_skill_status" in idx
        assert "idx_extensions_decision6" in idx
        assert "idx_extensions_active" in idx

    def test_status_default_is_proposed(self, ext_conn):
        eid = _ext_id()
        ext_conn.execute(
            "INSERT INTO ds_user_extensions (extension_id, skill_id, extension_type, content) "
            "VALUES (?, ?, ?, ?)",
            (eid, "ds-quality:security", "example", "{}"),
        )
        ext_conn.commit()
        row = ext_conn.execute(
            "SELECT status FROM ds_user_extensions WHERE extension_id = ?", (eid,)
        ).fetchone()
        assert row["status"] == "proposed"

    def test_past_wo_count_default_is_zero(self, ext_conn):
        eid = _ext_id()
        ext_conn.execute(
            "INSERT INTO ds_user_extensions (extension_id, skill_id, extension_type, content) "
            "VALUES (?, ?, ?, ?)",
            (eid, "ds-quality:security", "example", "{}"),
        )
        ext_conn.commit()
        row = ext_conn.execute(
            "SELECT past_wo_count FROM ds_user_extensions WHERE extension_id = ?", (eid,)
        ).fetchone()
        assert row["past_wo_count"] == 0


# ── CHECK constraint enforcement ──────────────────────────────────────────────


class TestCheckConstraints:
    def test_invalid_status_rejected(self, ext_conn):
        with pytest.raises(sqlite3.IntegrityError):
            _insert_ext(ext_conn, status="invalid_status")

    def test_valid_statuses_accepted(self, ext_conn):
        for status in (
            "proposed",
            "experimental",
            "active",
            "suppressed",
            "rejected",
            "deprecated",
        ):
            _insert_ext(ext_conn, status=status)
        count = ext_conn.execute("SELECT COUNT(*) FROM ds_user_extensions").fetchone()[0]
        assert count == 6

    def test_invalid_extension_type_rejected(self, ext_conn):
        with pytest.raises(sqlite3.IntegrityError):
            _insert_ext(ext_conn, extension_type="unknown_type")

    def test_valid_extension_types_accepted(self, ext_conn):
        for etype in (
            "example",
            "gap_filler",
            "threshold_override",
            "option_override",
            "mode_addition",
            "trigger_alias",
        ):
            _insert_ext(ext_conn, extension_type=etype)
        count = ext_conn.execute("SELECT COUNT(*) FROM ds_user_extensions").fetchone()[0]
        assert count == 6

    def test_baseline_eval_score_above_1_rejected(self, ext_conn):
        with pytest.raises(sqlite3.IntegrityError):
            _insert_ext(ext_conn, baseline_eval_score=1.5)

    def test_baseline_eval_score_below_0_rejected(self, ext_conn):
        with pytest.raises(sqlite3.IntegrityError):
            _insert_ext(ext_conn, baseline_eval_score=-0.1)

    def test_current_eval_score_above_1_rejected(self, ext_conn):
        with pytest.raises(sqlite3.IntegrityError):
            _insert_ext(ext_conn, current_eval_score=2.0)

    def test_valid_eval_scores_accepted(self, ext_conn):
        _insert_ext(ext_conn, baseline_eval_score=0.85, current_eval_score=0.90)
        _insert_ext(ext_conn, baseline_eval_score=0.0, current_eval_score=1.0)
        _insert_ext(ext_conn, baseline_eval_score=None, current_eval_score=None)
        count = ext_conn.execute("SELECT COUNT(*) FROM ds_user_extensions").fetchone()[0]
        assert count == 3

    def test_negative_past_wo_count_rejected(self, ext_conn):
        with pytest.raises(sqlite3.IntegrityError):
            _insert_ext(ext_conn, past_wo_count=-1)


# ── Decision 6 readiness query ────────────────────────────────────────────────


DECISION_6_QUERY = """
    SELECT * FROM ds_user_extensions
    WHERE status = 'experimental'
      AND past_wo_count >= 5
      AND current_eval_score >= baseline_eval_score * 0.95
      AND user_confirmed_at IS NOT NULL
"""


class TestDecision6Query:
    def _setup_fixtures(self, conn):
        """Plant 4 test rows covering the decision boundary cases."""
        # 1. experimental, N=4 (below threshold) → should NOT appear
        _insert_ext(
            conn,
            extension_id="ext-n4",
            status="experimental",
            past_wo_count=4,
            baseline_eval_score=0.85,
            current_eval_score=0.87,
            user_confirmed_at="2026-06-03T10:00:00",
        )
        # 2. experimental, N=5, good score, confirmed → SHOULD appear (Decision 6 eligible)
        _insert_ext(
            conn,
            extension_id="ext-eligible",
            status="experimental",
            past_wo_count=5,
            baseline_eval_score=0.85,
            current_eval_score=0.87,  # 0.87 >= 0.85 * 0.95 = 0.8075 ✓
            user_confirmed_at="2026-06-03T10:00:00",
        )
        # 3. active (already activated) → should NOT appear (wrong status)
        _insert_ext(
            conn,
            extension_id="ext-active",
            status="active",
            past_wo_count=7,
            baseline_eval_score=0.85,
            current_eval_score=0.90,
            user_confirmed_at="2026-06-03T09:00:00",
        )
        # 4. experimental, N=5, bad score (degraded) → should NOT appear
        _insert_ext(
            conn,
            extension_id="ext-degraded",
            status="experimental",
            past_wo_count=5,
            baseline_eval_score=0.85,
            current_eval_score=0.70,  # 0.70 < 0.85 * 0.95 = 0.8075 ✗
            user_confirmed_at="2026-06-03T10:00:00",
        )
        # 5. experimental, N=5, good score, NOT confirmed → should NOT appear
        _insert_ext(
            conn,
            extension_id="ext-unconfirmed",
            status="experimental",
            past_wo_count=5,
            baseline_eval_score=0.85,
            current_eval_score=0.87,
            user_confirmed_at=None,
        )

    def test_decision6_query_returns_only_eligible(self, ext_conn):
        """Only ext-eligible should match the Decision 6 query."""
        self._setup_fixtures(ext_conn)
        rows = ext_conn.execute(DECISION_6_QUERY).fetchall()
        ids = [r["extension_id"] for r in rows]
        assert ids == ["ext-eligible"], (
            f"Expected only ['ext-eligible'], got {ids}. "
            "Decision 6 gate is broken — fix schema before Phase 19.2+"
        )

    def test_n4_not_eligible(self, ext_conn):
        """N < 5 never activates automatically."""
        self._setup_fixtures(ext_conn)
        rows = ext_conn.execute(DECISION_6_QUERY).fetchall()
        assert "ext-n4" not in [r["extension_id"] for r in rows]

    def test_already_active_not_in_candidates(self, ext_conn):
        """active status excluded — already past the gate."""
        self._setup_fixtures(ext_conn)
        rows = ext_conn.execute(DECISION_6_QUERY).fetchall()
        assert "ext-active" not in [r["extension_id"] for r in rows]

    def test_degraded_score_not_eligible(self, ext_conn):
        """Score drop below 0.95 × baseline blocks activation."""
        self._setup_fixtures(ext_conn)
        rows = ext_conn.execute(DECISION_6_QUERY).fetchall()
        assert "ext-degraded" not in [r["extension_id"] for r in rows]

    def test_unconfirmed_not_eligible(self, ext_conn):
        """Extensions without human confirmation never activate."""
        self._setup_fixtures(ext_conn)
        rows = ext_conn.execute(DECISION_6_QUERY).fetchall()
        assert "ext-unconfirmed" not in [r["extension_id"] for r in rows]

    def test_empty_table_returns_empty(self, ext_conn):
        """Empty table → empty Decision 6 result (no error)."""
        rows = ext_conn.execute(DECISION_6_QUERY).fetchall()
        assert rows == []

    def test_tolerance_boundary_95pct(self, ext_conn):
        """Exactly at 0.95 × baseline (not below) → eligible."""
        _insert_ext(
            ext_conn,
            extension_id="ext-at-boundary",
            status="experimental",
            past_wo_count=5,
            baseline_eval_score=0.80,
            current_eval_score=0.76,  # 0.76 = 0.80 * 0.95 exactly ✓
            user_confirmed_at="2026-06-03T10:00:00",
        )
        rows = ext_conn.execute(DECISION_6_QUERY).fetchall()
        assert "ext-at-boundary" in [r["extension_id"] for r in rows]

    def test_one_below_boundary_not_eligible(self, ext_conn):
        """Just below 0.95 × baseline → not eligible."""
        _insert_ext(
            ext_conn,
            extension_id="ext-below-boundary",
            status="experimental",
            past_wo_count=5,
            baseline_eval_score=0.80,
            current_eval_score=0.759,  # 0.759 < 0.80 * 0.95 = 0.76 ✗
            user_confirmed_at="2026-06-03T10:00:00",
        )
        rows = ext_conn.execute(DECISION_6_QUERY).fetchall()
        assert "ext-below-boundary" not in [r["extension_id"] for r in rows]


# ── Additive constraint ───────────────────────────────────────────────────────


class TestAdditiveOnly:
    def test_migration_does_not_touch_canonical_skills(self):
        """Migration SQL must not contain any reference to canonical skill files."""
        sql_lower = MIGRATION_SQL.lower()
        forbidden = ["canonical/", "packs.yaml", "skill.md", "metadata.yml"]
        for f in forbidden:
            assert f not in sql_lower, (
                f"Migration 095 must not reference {f!r} — "
                "Phase 19 is additive only; canonical skills must not be modified"
            )

    def test_migration_only_creates_new_tables(self):
        """Migration must only CREATE new objects, not DROP or ALTER existing ones."""
        sql_upper = MIGRATION_SQL.upper()
        # These would modify existing Phase 18 objects
        assert "DROP TABLE" not in sql_upper
        assert "ALTER TABLE" not in sql_upper
        # CREATE TABLE IF NOT EXISTS is fine (idempotent)
        assert "CREATE TABLE IF NOT EXISTS DS_USER_EXTENSIONS" in sql_upper
