"""Tests for core.config.seat_providers."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import seat_providers, state


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("DREAM_STUDIO_HOME", raising=False)
    return tmp_path


def test_get_seat_provider_missing_returns_none():
    assert seat_providers.get_seat_provider("security-review") is None


def test_all_seat_providers_empty_by_default():
    assert seat_providers.all_seat_providers() == {}


def test_set_seat_provider_round_trips():
    seat_providers.set_seat_provider("security-review", provider="codex", model="opus")
    assert seat_providers.get_seat_provider("security-review") == {
        "provider": "codex",
        "model": "opus",
    }
    assert seat_providers.all_seat_providers() == {
        "security-review": {"provider": "codex", "model": "opus"}
    }


def test_set_seat_provider_without_model_omits_it():
    seat_providers.set_seat_provider("security-review", provider="codex")
    assert seat_providers.get_seat_provider("security-review") == {"provider": "codex"}


def test_set_seat_provider_claude_code_is_a_valid_provider():
    seat_providers.set_seat_provider("security-review", provider="claude_code", model="haiku")
    assert seat_providers.get_seat_provider("security-review") == {
        "provider": "claude_code",
        "model": "haiku",
    }


def test_set_seat_provider_unknown_provider_raises():
    with pytest.raises(ValueError, match="unknown provider"):
        seat_providers.set_seat_provider("security-review", provider="not-a-real-tool")


def test_set_seat_provider_unknown_model_alias_raises_for_claude_code():
    with pytest.raises(ValueError, match="unknown model alias"):
        seat_providers.set_seat_provider("security-review", provider="claude_code", model="ultra")


def test_set_seat_provider_unknown_model_alias_raises_for_multitool_target():
    with pytest.raises(KeyError):
        seat_providers.set_seat_provider("security-review", provider="codex", model="ultra")


def test_set_seat_provider_effort_raises_when_tool_declares_none():
    # No TargetSpec has a populated effort_levels yet (see registry.py's own
    # comment) -- any effort argument today must raise, not silently accept one.
    with pytest.raises(ValueError, match="declares no effort_levels"):
        seat_providers.set_seat_provider("security-review", provider="codex", effort="high")


def test_set_seat_provider_effort_raises_for_claude_code():
    with pytest.raises(ValueError, match="no reasoning-effort concept"):
        seat_providers.set_seat_provider("security-review", provider="claude_code", effort="high")


def test_set_seat_provider_empty_seat_name_raises():
    with pytest.raises(ValueError, match="seat must be non-empty"):
        seat_providers.set_seat_provider("   ", provider="codex")


def test_set_seat_provider_overwrites_existing_pin():
    seat_providers.set_seat_provider("security-review", provider="codex", model="opus")
    seat_providers.set_seat_provider("security-review", provider="gemini_cli", model="sonnet")
    assert seat_providers.get_seat_provider("security-review") == {
        "provider": "gemini_cli",
        "model": "sonnet",
    }


def test_set_seat_provider_does_not_disturb_other_seats():
    seat_providers.set_seat_provider("security-review", provider="codex")
    seat_providers.set_seat_provider("architecture", provider="gemini_cli")
    assert seat_providers.all_seat_providers() == {
        "security-review": {"provider": "codex"},
        "architecture": {"provider": "gemini_cli"},
    }


def test_clear_seat_provider_removes_pin():
    seat_providers.set_seat_provider("security-review", provider="codex")
    seat_providers.clear_seat_provider("security-review")
    assert seat_providers.get_seat_provider("security-review") is None


def test_clear_seat_provider_on_unpinned_seat_is_a_noop():
    seat_providers.clear_seat_provider("never-pinned")
    assert seat_providers.all_seat_providers() == {}


def test_clear_seat_provider_does_not_disturb_other_seats():
    seat_providers.set_seat_provider("security-review", provider="codex")
    seat_providers.set_seat_provider("architecture", provider="gemini_cli")
    seat_providers.clear_seat_provider("security-review")
    assert seat_providers.all_seat_providers() == {"architecture": {"provider": "gemini_cli"}}


def test_set_seat_provider_does_not_disturb_unrelated_config_keys():
    state.write_config({"director_name": "Alice"})
    seat_providers.set_seat_provider("security-review", provider="codex")
    cfg = state.read_config()
    assert cfg["director_name"] == "Alice"
    assert cfg["seat_providers"] == {"security-review": {"provider": "codex"}}


def test_set_seat_provider_invalid_model_does_not_persist_a_partial_pin():
    with pytest.raises(KeyError):
        seat_providers.set_seat_provider("security-review", provider="codex", model="ultra")
    assert seat_providers.get_seat_provider("security-review") is None
