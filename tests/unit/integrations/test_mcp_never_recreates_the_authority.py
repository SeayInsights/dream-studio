"""A long-running MCP server never re-creates a vanished authority.

`ds_work_order_add_task` reached core.work_orders.mutations.add_task, which read the
work order's context through a raw sqlite3.connect(): with the authority gone from an
installed home, that open created a new, empty studio.db under the running server.
"""

from __future__ import annotations

import gc
from pathlib import Path

from core.config.sqlite_bootstrap import CREATE_AUTHORITY_ENV, bootstrap_database
from integrations.mcp.auth import Identity
from integrations.mcp.server import handle_message


def _call(home: Path, name: str, arguments: dict, identity: Identity) -> dict:
    return handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        dream_studio_home=home,
        identity=identity,
    )


def test_add_task_after_the_authority_vanished_creates_nothing(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    db = home / "state" / "studio.db"
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DREAM_STUDIO_APPLY_UNRELEASED", "1")
    monkeypatch.setenv(CREATE_AUTHORITY_ENV, str(db))
    bootstrap_database(db)
    monkeypatch.delenv(CREATE_AUTHORITY_ENV)
    (home / "state" / "installed-version").write_text("0.1.0 abc\n", encoding="utf-8")
    gateway = Identity(name="gateway", capabilities=frozenset({"work_order:add_task"}))

    # The server has been running against the real authority...
    assert "result" in _call(home, "ds_project_state", {}, gateway)
    # ...and then it disappears.
    gc.collect()  # a read path that let a connection go out of scope without closing it
    for suffix in ("", "-wal", "-shm"):
        part = Path(f"{db}{suffix}")
        if part.exists():
            part.unlink()

    _call(
        home,
        "ds_work_order_add_task",
        {"work_order_id": "wo-1", "title": "a task", "acceptance_criteria": "TEST-CHECK: x"},
        gateway,
    )
    assert not db.exists(), "the MCP call re-created the authority"
