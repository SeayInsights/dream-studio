from __future__ import annotations
import pytest


def test_spool_state_enum_completeness():
    from spool.states import SpoolState

    values = {s.value for s in SpoolState}
    assert "spool" in values
    assert "processing" in values
    assert "processed" in values
    assert "failed" in values
    assert len(values) == 4


def test_state_dir_resolution(spool_root):
    from spool.states import SpoolState, state_dir

    for state in SpoolState:
        d = state_dir(state, spool_root)
        assert d.parent == spool_root
        assert d.name == state.value


def test_sessions_dir_resolution(spool_root):
    from spool.states import sessions_dir

    d = sessions_dir(spool_root)
    assert d.parent == spool_root
    assert d.name == ".sessions"


def test_ensure_dirs_creates_all(spool_root):
    from spool.states import SpoolState, ensure_dirs, state_dir, sessions_dir

    ensure_dirs(spool_root)
    for state in SpoolState:
        assert state_dir(state, spool_root).exists()
    assert sessions_dir(spool_root).exists()
