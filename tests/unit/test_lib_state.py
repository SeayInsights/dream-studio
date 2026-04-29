"""Tests for hooks/lib/state.py — atomic write, config/pulse I/O, quiet mode."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.state import (  # noqa: E402
    SchemaVersionError,
    _atomic_write,
    get_quiet_mode,
    read_config,
    read_pulse,
    set_quiet_mode,
    write_config,
    write_pulse,
)


# ── _atomic_write exception cleanup (lines 57-62) ─────────────────────────


def test_atomic_write_cleanup_on_replace_failure(tmp_path, monkeypatch):
    path = tmp_path / ".dream-studio" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    def fail_replace(*a):
        raise OSError("replace failed")
    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        _atomic_write(path, {"key": "value"})


def test_atomic_write_cleanup_unlink_also_fails(tmp_path, monkeypatch):
    path = tmp_path / ".dream-studio" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    def fail_replace(*a):
        raise OSError("replace failed")
    def fail_unlink(*a):
        raise OSError("unlink failed")
    monkeypatch.setattr(os, "replace", fail_replace)
    monkeypatch.setattr(os, "unlink", fail_unlink)
    with pytest.raises(OSError):
        _atomic_write(path, {"key": "value"})


# ── read_config: corrupt JSON returns default (lines 73-74) ───────────────


def test_read_config_corrupt_json_returns_default(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config = tmp_path / ".dream-studio" / "config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("NOT VALID JSON", encoding="utf-8")
    result = read_config()
    assert result == {"schema_version": 1}


# ── read_pulse: corrupt JSON returns empty dict (lines 94-95) ─────────────


def test_read_pulse_corrupt_json_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    pulse = tmp_path / ".dream-studio" / "meta" / "pulse-latest.json"
    pulse.parent.mkdir(parents=True, exist_ok=True)
    pulse.write_text("INVALID", encoding="utf-8")
    result = read_pulse()
    assert result == {}


# ── get_quiet_mode: non-integer value returns 0 (lines 111-112) ───────────


def test_get_quiet_mode_non_integer_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    write_config({"quiet_mode": "not-a-number"})
    assert get_quiet_mode() == 0


# ── set_quiet_mode: persists and clamps (lines 124-126) ───────────────────


def test_set_quiet_mode_persists_value(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    set_quiet_mode(3)
    assert get_quiet_mode() == 3


def test_set_quiet_mode_clamps_negative_to_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    set_quiet_mode(-5)
    assert get_quiet_mode() == 0


# ── SchemaVersionError: future schema raises (existing behavior guard) ─────


def test_read_config_future_schema_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config = tmp_path / ".dream-studio" / "config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text('{"schema_version": 999}', encoding="utf-8")
    with pytest.raises(SchemaVersionError):
        read_config()


def test_write_pulse_and_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    write_pulse({"score": 42, "ts": "2026-01-01"})
    result = read_pulse()
    assert result["score"] == 42
