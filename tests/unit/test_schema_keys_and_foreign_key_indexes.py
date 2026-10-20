"""Every table has a primary key, and every foreign-key column is indexed.

The rule: a join or a parent-side delete must never scan the child table. Every table
already had a primary key. 6 declared FOREIGN KEY columns and 19 columns that name another
table's key (milestone_id, task_id, adapter_id, session_id, ...) had no index that leads
with them until migration 160. These tests run against a database built by the real
migration chain, so they judge the schema that ships, and fail when the next table or
migration breaks the rule.
"""

from __future__ import annotations

import sqlite3

import pytest

from core.config.sqlite_bootstrap import run_migrations

#: Columns that look like a foreign key and are deliberately unindexed. Empty, and it may
#: only shrink: an entry is a reviewed reason, not a way to make the test pass.
CONVENTION_FK_ALLOWLIST: frozenset[tuple[str, str]] = frozenset()


@pytest.fixture(scope="module")
def schema() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


def _base_tables(conn) -> list[str]:
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    virtual = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE 'CREATE VIRTUAL%'"
        )
    }
    # An FTS virtual table owns shadow tables (<name>_data, _idx, _docsize, ...): none of
    # them is a table anyone designs, and they have no key to declare.
    return [
        t for t in tables if t not in virtual and not any(t.startswith(v + "_") for v in virtual)
    ]


def _primary_key(conn, table: str) -> list[str]:
    cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [r[1] for r in sorted(cols, key=lambda r: r[5]) if r[5]]


def _leading_columns(conn, table: str) -> set[str]:
    """Columns an index (partial ones included) or the primary key leads with."""
    leading = set(_primary_key(conn, table)[:1])
    for index in conn.execute(f'PRAGMA index_list("{table}")').fetchall():
        info = conn.execute(f'PRAGMA index_info("{index[1]}")').fetchall()
        if info:
            leading.add(info[0][2])
    return leading


def test_every_table_has_a_primary_key(schema):
    keyless = [t for t in _base_tables(schema) if not _primary_key(schema, t)]
    assert keyless == [], f"tables with no PRIMARY KEY: {keyless}"


def test_every_declared_foreign_key_column_is_indexed(schema):
    missing = []
    for table in _base_tables(schema):
        leading = _leading_columns(schema, table)
        for fk in schema.execute(f'PRAGMA foreign_key_list("{table}")').fetchall():
            if fk[3] not in leading:
                missing.append(f"{table}.{fk[3]} -> {fk[2]}")
    assert missing == [], (
        "FOREIGN KEY columns with no index that leads with them (add a CREATE INDEX in a "
        f"migration): {missing}"
    )


def test_every_column_naming_another_tables_key_is_indexed(schema):
    """The columns that are foreign keys in everything but declaration.

    A column ending in _id whose name is another table's single-column primary key is a
    reference. They are not declared (SQLite cannot add a FOREIGN KEY without rebuilding
    the table), so the declared-FK test cannot see them: 19 went unindexed. A column in its
    own table's key, or already leading an index, is fine.
    """
    tables = _base_tables(schema)
    single_key = {}
    for table in tables:
        key = _primary_key(schema, table)
        if len(key) == 1:
            single_key.setdefault(key[0], []).append(table)
    missing = []
    for table in tables:
        leading = _leading_columns(schema, table)
        own_key = set(_primary_key(schema, table))
        for column in (r[1] for r in schema.execute(f'PRAGMA table_info("{table}")')):
            if (
                column.endswith("_id")
                and column in single_key
                and column not in own_key
                and column not in leading
                and (table, column) not in CONVENTION_FK_ALLOWLIST
            ):
                missing.append(f"{table}.{column} (a key of {', '.join(single_key[column][:3])})")
    assert missing == [], f"reference columns with no index (add one in a migration): {missing}"


def test_the_allowlist_holds_no_stale_entries(schema):
    """An allowlist entry for a column that no longer exists, or is now indexed, is noise
    that would hide a future regression of the same name."""
    stale = []
    for table, column in CONVENTION_FK_ALLOWLIST:
        columns = [r[1] for r in schema.execute(f'PRAGMA table_info("{table}")')]
        if column not in columns or column in _leading_columns(schema, table):
            stale.append((table, column))
    assert stale == []


def test_the_migration_is_idempotent_and_its_rollback_drops_only_its_indexes(tmp_path):
    """Re-running 160 changes nothing, and the paired rollback removes exactly what it
    added and no table or row."""
    import pathlib
    import re

    migrations = pathlib.Path("core/event_store/migrations")
    forward = (migrations / "160_index_foreign_key_columns.sql").read_text(encoding="utf-8")
    rollback = (migrations / "rollback" / "160_index_foreign_key_columns.sql").read_text(
        encoding="utf-8"
    )
    created = set(re.findall(r"^CREATE INDEX IF NOT EXISTS (\w+)", forward, re.M))
    dropped = set(re.findall(r"^DROP INDEX IF EXISTS (\w+)", rollback, re.M))
    assert created and created == dropped

    conn = sqlite3.connect(":memory:")
    run_migrations(conn)

    def indexes() -> set[str]:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}

    def tables() -> set[str]:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    assert created <= indexes()
    before = (indexes(), tables())
    conn.executescript(forward)  # again
    assert (indexes(), tables()) == before
    conn.executescript(rollback)
    assert indexes() == before[0] - created
    assert tables() == before[1]
    conn.close()
