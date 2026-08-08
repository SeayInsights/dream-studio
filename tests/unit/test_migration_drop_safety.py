"""WO dbcaa64f: the migration-risk gate blocks unguarded DROP TABLE in forward migrations.

The raw_runtime_state / migration-150 finding: a DROP that rests on a prose "never released /
empty" claim rather than in-file evidence is a DATA_LOSS risk. This gate forces the safety basis
into the migration file itself (a backup/copy, or an explicit reviewed DROP-SAFETY rationale).
"""

from __future__ import annotations

from core.gates.migration_risk import unguarded_drop_violations


def test_unguarded_drop_is_flagged():
    sql = "-- Migration 200: drop foo\n\nDROP TABLE IF EXISTS foo;\n"
    violations = unguarded_drop_violations(sql)
    assert len(violations) == 1
    assert "foo" in violations[0]


def test_drop_with_safety_rationale_passes():
    sql = (
        "-- Migration 200: drop foo\n"
        "-- DROP-SAFETY: foo is a dead table, rows=0 verified in prod; no live writer.\n\n"
        "DROP TABLE IF EXISTS foo;\n"
    )
    assert unguarded_drop_violations(sql) == []


def test_drop_with_backup_copy_passes():
    sql = "CREATE TABLE foo_backup AS SELECT * FROM foo;\nDROP TABLE foo;\n"
    assert unguarded_drop_violations(sql) == []


def test_drop_with_insert_copy_into_target_passes():
    sql = "INSERT INTO ds_config (key, value) SELECT key, value FROM foo;\nDROP TABLE foo;\n"
    assert unguarded_drop_violations(sql) == []


def test_no_drop_no_violation():
    sql = "CREATE TABLE bar (id TEXT PRIMARY KEY);\nINSERT INTO bar (id) VALUES ('x');\n"
    assert unguarded_drop_violations(sql) == []


def test_multiple_unguarded_drops_each_flagged():
    sql = "DROP TABLE a;\nDROP TABLE IF EXISTS b;\n"
    violations = unguarded_drop_violations(sql)
    assert len(violations) == 2
