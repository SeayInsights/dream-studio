"""An install marker one test writes into the session home does not mark it for the next.

The two tests run in file order: the first leaves `state/installed-version` in the
session's shared Dream Studio home, as an install test does; the second creates a fresh
configured authority, which the guard would refuse in a home that still carried it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _session_home() -> Path:
    """The session home conftest itself created, with no marker in it yet; skip otherwise.

    A home that came in through the environment may be an operator's: nothing here
    writes into it, and an existing marker is never overwritten.
    """
    made = os.environ.get("DREAM_STUDIO_TEST_SESSION_HOME")
    if not made or os.environ.get("DREAM_STUDIO_HOME") != made:
        pytest.skip("DREAM_STUDIO_HOME is not the session home conftest created")
    home = Path(made)
    if (home / "state" / "installed-version").exists():
        pytest.skip("the session home already carries a marker; never overwrite it")
    return home


def test_a_test_that_installs_leaves_a_marker_behind():
    home = _session_home()
    (home / "state").mkdir(parents=True, exist_ok=True)
    with open(home / "state" / "installed-version", "x", encoding="utf-8") as marker:
        marker.write("0.1.0 abc\n")


def test_the_next_test_can_still_create_its_own_authority(tmp_path, monkeypatch):
    from core.config.database import DatabaseRuntime
    from core.event_store.connection import _connect

    db = tmp_path / "studio.db"
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    DatabaseRuntime.reset_instance()
    _connect(db).close()
    assert db.is_file()
