"""WO-SPLIT-STUDIO-DB: migration_runner module (split from studio_db.py)."""

from __future__ import annotations
import argparse
import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import (
    migrations_dir as _canonical_migrations_dir,
    run_migrations as _canonical_run_migrations,
    split_statements as _canonical_split_statements,
)

from .connection import _connect
from .event_writer import import_buffer, rolling_window_prune


def _split_statements(sql_text: str) -> list[str]:
    """Split SQL into individual statements, respecting trigger BEGIN/END blocks."""
    return _canonical_split_statements(sql_text)


def _migrations_dir() -> Path:
    return _canonical_migrations_dir()


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Apply pending schema migrations from core/event_store/migrations/*.sql."""
    _canonical_run_migrations(conn)


def schema_version(db_path: Path | None = None) -> int:
    try:
        c = _connect(db_path)
        try:
            v = c.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] or 0
            return v
        finally:
            c.close()
    except Exception:
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="studio_db CLI")
    sub = ap.add_subparsers(dest="cmd")
    # skill-correct subcommand removed — cor_skill_corrections dropped migration 131
    ib = sub.add_parser("import-and-rebuild")
    ib.add_argument("--buffer", required=True)
    sub.add_parser("prune")
    sub.add_parser("status")
    args = ap.parse_args()
    if args.cmd == "import-and-rebuild":
        n = import_buffer(Path(args.buffer))
        print(f"imported {n} rows")
    elif args.cmd == "prune":
        print(f"pruned {rolling_window_prune()} rows")
    elif args.cmd == "status":
        c = _connect()
        tables = [
            # raw_workflow_runs, raw_workflow_nodes dropped migration 141 (WO 9f47a1a0)
            "raw_skill_telemetry",
            # cor_skill_corrections dropped migration 131
            # sum_skill_summary dropped migration 140 (derived; see get_skill_summaries)
            "log_batch_imports",
            "raw_operational_snapshots",
            "raw_approaches",
            "reg_gotchas",
            "reg_projects",
            "raw_sessions",
            "raw_handoffs",
            "raw_lessons",
            "raw_sentinels",
            # raw_token_usage dropped migration 138
            "_schema_version",
        ]
        v = c.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] or 0
        print(f"Schema version: {v}")
        fk = c.execute("PRAGMA foreign_keys").fetchone()[0]
        print(f"Foreign keys: {'ON' if fk else 'OFF'}")
        print(f"\n{'Table':<30} {'Rows':>8}\n" + "-" * 40)
        for t in tables:
            try:
                n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608
                print(f"{t:<30} {n:>8}")
            except sqlite3.OperationalError:
                print(f"{t:<30} {'N/A':>8}")
        c.close()
    else:
        ap.print_help()
