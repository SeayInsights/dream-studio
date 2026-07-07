"""WO-SPLIT-STUDIO-DB: core/event_store/studio_db.py was split into connection /
event_writer / event_reader / migration_runner behind a facade that re-exports the
public API (and the private helpers external callers historically imported). These
tests pin the facade contract, module independence, decorator survival, and a
write/read roundtrip, so the 130+ `from core.event_store.studio_db import X` callers
keep working.
"""

from __future__ import annotations

import importlib
import tempfile
import uuid
from pathlib import Path

# The names callers import from studio_db (public + the compat privates).
_PUBLIC_API = [
    "insert_lesson",
    "get_lessons",
    "insert_session",
    "get_session",
    "insert_approach",
    "upsert_project",
    "get_project",
    "schema_version",
    "import_buffer",
    "rolling_window_prune",
]
_COMPAT_PRIVATE = [
    "_connect",
    "_db_path",
    "_run_migrations",
    "_split_statements",
    "_migrations_dir",
]
_SUBMODULES = [
    "core.event_store.connection",
    "core.event_store.event_writer",
    "core.event_store.event_reader",
    "core.event_store.migration_runner",
]


def test_facade_reexports_public_and_compat_names():
    s = importlib.import_module("core.event_store.studio_db")
    missing = [n for n in (_PUBLIC_API + _COMPAT_PRIVATE) if not hasattr(s, n)]
    assert not missing, f"facade dropped names callers import: {missing}"


def test_submodules_import_independently():
    for mod in _SUBMODULES:
        assert importlib.import_module(mod) is not None


def test_db_transaction_is_a_context_manager():
    """The @contextmanager decorator must survive the extraction."""
    from core.event_store.connection import _db_transaction

    db = Path(tempfile.mkdtemp()) / "s.db"
    with _db_transaction(db) as conn:
        conn.execute("SELECT 1")


def test_connect_runs_migrations():
    """_connect (connection) calls _run_migrations (migration_runner) across the
    module boundary — the local-import cycle break must work at runtime."""
    from core.event_store.connection import _connect
    from core.event_store.studio_db import schema_version

    db = Path(tempfile.mkdtemp()) / "s.db"
    conn = _connect(db)
    conn.close()
    assert schema_version(db) > 0, "migrations did not run through the split _connect"


def test_write_read_roundtrip_through_facade():
    """A lesson written and read back through the facade proves the writer/reader
    split preserves behavior end to end."""
    from core.event_store.studio_db import get_lessons, insert_lesson

    db = Path(tempfile.mkdtemp()) / "s.db"
    lid = str(uuid.uuid4())
    insert_lesson(lesson_id=lid, source="test", title="roundtrip", lesson="x", db_path=db)
    rows = get_lessons(db_path=db)
    assert any(r.get("lesson_id") == lid for r in rows), "written lesson not read back via facade"


def test_facade_is_a_thin_shell():
    import core.event_store.studio_db as s

    src = Path(s.__file__).read_text(encoding="utf-8")
    assert "def insert_lesson" not in src, "implementation leaked into the facade"
    # Pure re-exports + __all__ (no function bodies) — a shell even at ~130 lines.
    assert src.count("\n") < 200, "facade should be a thin re-export shell"
