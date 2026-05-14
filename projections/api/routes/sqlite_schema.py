"""Small SQLite schema probes for dashboard route compatibility.

These helpers intentionally inspect object metadata only. They do not create,
migrate, or repair database objects.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_identifier(name: str) -> str:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"Unsafe SQLite identifier: {name!r}")
    return f'"{name}"'


def object_type(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute(
        "SELECT type FROM sqlite_master WHERE name = ? AND type IN ('table', 'view')",
        (name,),
    ).fetchone()
    return str(row["type"] if isinstance(row, sqlite3.Row) else row[0]) if row else None


def object_exists(conn: sqlite3.Connection, name: str) -> bool:
    return object_type(conn, name) is not None


def table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    if not object_exists(conn, name):
        return set()
    quoted = quote_identifier(name)
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({quoted})")}


def has_columns(conn: sqlite3.Connection, name: str, columns: Iterable[str]) -> bool:
    available = table_columns(conn, name)
    return all(column in available for column in columns)


def missing_columns(conn: sqlite3.Connection, name: str, columns: Iterable[str]) -> list[str]:
    available = table_columns(conn, name)
    return [column for column in columns if column not in available]


def count_rows(conn: sqlite3.Connection, name: str) -> int:
    if not object_exists(conn, name):
        return 0
    quoted = quote_identifier(name)
    return int(conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0] or 0)


def latest_value(conn: sqlite3.Connection, name: str, column: str) -> str | None:
    if not has_columns(conn, name, [column]):
        return None
    quoted_table = quote_identifier(name)
    quoted_column = quote_identifier(column)
    row = conn.execute(f"SELECT MAX({quoted_column}) FROM {quoted_table}").fetchone()
    if not row:
        return None
    value = row[0]
    return str(value) if value is not None else None


def source_status(
    classification: str,
    reason: str,
    *,
    source_tables: Iterable[str] = (),
    missing: Iterable[str] = (),
) -> dict[str, object]:
    return {
        "classification": classification,
        "reason": reason,
        "source_tables": list(source_tables),
        "missing": list(missing),
        "derived_view": True,
        "primary_authority": False,
    }
