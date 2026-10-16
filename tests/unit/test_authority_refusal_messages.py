"""What the operator is told when the authority is gone.

Every CLI path that needs the authority said "Run rehearsal-install first" -- in an
installed home that advice re-creates an empty authority over the lost one. And a
hook that hit the guard's refusal swallowed it into a fallback file, so nobody in the
session ever learned that every write was failing.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest


@pytest.fixture
def marked_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    (home / "state" / "backups" / "self-install-x").mkdir(parents=True)
    (home / "state" / "backups" / "self-install-x" / "studio.db").write_bytes(b"x")
    time.sleep(0.01)
    (home / "state" / "studio.db.bak").write_bytes(b"y")
    (home / "state" / "installed-version").write_text("0.1.0 abc\n", encoding="utf-8")
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(home / "state" / "studio.db"))
    monkeypatch.delenv("DREAM_STUDIO_CREATE_AUTHORITY", raising=False)
    return home


def test_cli_paths_never_advise_rehearsal_install_in_an_installed_home(marked_home):
    from core.projects.queries import get_project_list

    with pytest.raises(RuntimeError) as excinfo:
        get_project_list(source_root=Path("."), dream_studio_home=marked_home)
    message = str(excinfo.value)
    assert "rehearsal-install" not in message
    assert f"ds --home {marked_home} restore <dir> --execute" in message
    # Every backup present, newest first.
    bak = str(marked_home / "state" / "studio.db.bak")
    directory = str(marked_home / "state" / "backups" / "self-install-x")
    assert bak in message and directory in message
    assert message.index(bak) < message.index(directory)


def test_a_fresh_home_still_gets_the_bootstrap_hint(tmp_path):
    from core.projects.queries import get_project_list

    with pytest.raises(RuntimeError, match="rehearsal-install"):
        get_project_list(source_root=Path("."), dream_studio_home=tmp_path / "fresh")


def test_a_hook_surfaces_the_refusal_once_per_session(marked_home, capsys):
    from core.event_store.event_writer_hooks import insert_hook_execution

    for _ in range(3):
        assert (
            insert_hook_execution(
                "on-x", "PostToolUse", {}, "2026-10-16T00:00:00+00:00", session_id="s-1"
            )
            == -1
        )
    err = capsys.readouterr().err
    assert err.count("Refusing to create") == 1, err
    insert_hook_execution("on-x", "PostToolUse", {}, "2026-10-16T00:00:00+00:00", session_id="s-2")
    assert capsys.readouterr().err.count("Refusing to create") == 1
