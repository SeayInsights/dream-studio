"""An install marker one test writes into the session home does not mark it for the next.

The two tests run in file order: the first leaves `state/installed-version` in the
session's shared Dream Studio home, as an install test does; the second creates a fresh
configured authority, which the guard would refuse in a home that still carried it.
"""

from __future__ import annotations

import os
from pathlib import Path


def test_a_test_that_installs_leaves_a_marker_behind():
    home = Path(os.environ["DREAM_STUDIO_HOME"])
    (home / "state").mkdir(parents=True, exist_ok=True)
    (home / "state" / "installed-version").write_text("0.1.0 abc\n", encoding="utf-8")


def test_the_next_test_can_still_create_its_own_authority(tmp_path, monkeypatch):
    from core.config.database import DatabaseRuntime
    from core.event_store.connection import _connect

    db = tmp_path / "studio.db"
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    DatabaseRuntime.reset_instance()
    _connect(db).close()
    assert db.is_file()
