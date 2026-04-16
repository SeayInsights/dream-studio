"""Tests for hooks.lib.state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib import state


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def test_read_config_missing_returns_default():
    doc = state.read_config()
    assert doc == {"schema_version": state.SCHEMA_VERSION}


def test_write_config_persists_and_stamps_schema(isolated_home):
    path = state.write_config({"director_name": "Alice"})
    assert path == isolated_home / ".dream-studio" / "config.json"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["director_name"] == "Alice"
    assert written["schema_version"] == state.SCHEMA_VERSION


def test_read_config_round_trip():
    state.write_config({"director_name": "Bob", "opt_in_notion": False})
    doc = state.read_config()
    assert doc["director_name"] == "Bob"
    assert doc["opt_in_notion"] is False
    assert doc["schema_version"] == state.SCHEMA_VERSION


def test_read_config_rejects_newer_schema(isolated_home):
    config_path = isolated_home / ".dream-studio" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps({"schema_version": state.SCHEMA_VERSION + 1}),
        encoding="utf-8",
    )
    with pytest.raises(state.SchemaVersionError):
        state.read_config()


def test_read_pulse_missing_returns_empty_dict():
    assert state.read_pulse() == {}


def test_write_pulse_persists_and_stamps_schema(isolated_home):
    path = state.write_pulse({"health": "HEALTHY", "stale_branches": 0})
    assert path == isolated_home / ".dream-studio" / "meta" / "pulse-latest.json"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["health"] == "HEALTHY"
    assert written["schema_version"] == state.SCHEMA_VERSION


def test_read_pulse_round_trip():
    state.write_pulse({"health": "HEALTHY", "open_prs": 2})
    doc = state.read_pulse()
    assert doc["health"] == "HEALTHY"
    assert doc["open_prs"] == 2


def test_read_pulse_rejects_newer_schema(isolated_home):
    pulse_path = isolated_home / ".dream-studio" / "meta" / "pulse-latest.json"
    pulse_path.parent.mkdir(parents=True, exist_ok=True)
    pulse_path.write_text(
        json.dumps({"schema_version": state.SCHEMA_VERSION + 1}),
        encoding="utf-8",
    )
    with pytest.raises(state.SchemaVersionError):
        state.read_pulse()


def test_read_config_rejects_non_integer_schema(isolated_home):
    config_path = isolated_home / ".dream-studio" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps({"schema_version": "v1"}),
        encoding="utf-8",
    )
    with pytest.raises(state.SchemaVersionError):
        state.read_config()
