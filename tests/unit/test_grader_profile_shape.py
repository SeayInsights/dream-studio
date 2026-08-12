"""WO-GRADER-PROFILE-REGISTRY tasks 2-4: the grader provider profile resolver defines a
profile shape resolvable without network, selects per-role with fallback to a default,
and fails closed when nothing resolves.
"""

from __future__ import annotations

import pytest

from config.grader_profiles import (
    UnresolvableGraderProfile,
    resolve_grader_profile,
)


def test_profile_resolves_without_network(monkeypatch):
    # No env overrides; pure static-config resolution (no network, no DB).
    for key in list(__import__("os").environ):
        if key.startswith("DS_GRADER_PROFILE_"):
            monkeypatch.delenv(key, raising=False)
    profile = resolve_grader_profile("correctness")
    assert isinstance(profile, dict)
    assert profile.get("command"), "a resolved profile must name a provider command"
    assert "prompt_via" in profile


def test_per_role_override_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("DS_GRADER_PROFILE_COMPLETION", raising=False)
    table = {
        "default": {"command": "claude", "print_flag": "--print", "prompt_via": "stdin"},
        "correctness": {"command": "second-grader", "prompt_via": "stdin"},
    }
    # A role WITH an entry gets its own profile.
    assert resolve_grader_profile("correctness", profiles=table)["command"] == "second-grader"
    # A role WITHOUT an entry falls back to the default.
    assert resolve_grader_profile("completion", profiles=table)["command"] == "claude"


def test_per_role_env_override_wins(monkeypatch):
    table = {"default": {"command": "claude", "print_flag": "--print", "prompt_via": "stdin"}}
    monkeypatch.setenv("DS_GRADER_PROFILE_CORRECTNESS", "my-grader --grade")
    resolved = resolve_grader_profile("correctness", profiles=table)
    assert resolved["command"] == "my-grader"
    assert resolved["base_args"] == ["--grade"]


def test_unresolvable_profile_fails_closed(monkeypatch):
    monkeypatch.delenv("DS_GRADER_PROFILE_GHOST", raising=False)
    # No entry for the role and no default -> fail closed (raise), never spawn nothing.
    with pytest.raises(UnresolvableGraderProfile):
        resolve_grader_profile("ghost", profiles={})
