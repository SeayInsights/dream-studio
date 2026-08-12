"""WO-GRADER-PROFILE-REGISTRY (+ gap follow-ups): the grader provider profile resolver.

Covers the original tasks (shape resolvable without network, per-role fallback to default,
fail closed) and the gap-WO completions: minimum profile fields, model_id fed to the runner
argv, the full precedence chain (stub > CLI > env > config file > default), a fail-closed
message that names the exact keys, and the inspectable role->provider mapping.
"""

from __future__ import annotations

import json
import os

import pytest

from config.grader_profiles import (
    GRADER_ROLES,
    UnresolvableGraderProfile,
    describe_grader_selection,
    resolve_grader_profile,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Isolate every test from ambient grader-profile env vars."""
    for key in list(os.environ):
        if key.startswith("DS_GRADER_PROFILE_") or key == "DS_GRADER_STUB":
            monkeypatch.delenv(key, raising=False)


# ── original task ACs ───────────────────────────────────────────────────────────


def test_profile_resolves_without_network():
    profile = resolve_grader_profile("correctness")
    assert isinstance(profile, dict)
    assert profile.get("command")
    assert "prompt_via" in profile


def test_per_role_override_falls_back_to_default():
    table = {
        "default": {"command": "claude", "print_flag": "--print", "prompt_via": "stdin"},
        "correctness": {"command": "second-grader", "prompt_via": "stdin"},
    }
    assert resolve_grader_profile("correctness", profiles=table)["command"] == "second-grader"
    assert resolve_grader_profile("completion", profiles=table)["command"] == "claude"


def test_unresolvable_profile_fails_closed():
    with pytest.raises(UnresolvableGraderProfile):
        resolve_grader_profile("ghost", profiles={})


# ── gap: minimum profile fields ───────────────────────────────────────────────


def test_profile_carries_minimum_fields():
    profile = resolve_grader_profile("completion")
    for key in ("provider_id", "command", "model_id", "availability_probe", "prompt_via"):
        assert key in profile, f"profile must carry {key}"


# ── gap: model id fed through to the runner argv ──────────────────────────────


def test_model_id_flows_into_runner_argv():
    from core.adapters.grader_runner import resolve_grader_argv

    profile = {"command": "prov", "model_flag": "--model", "model_id": "m-123"}
    argv = resolve_grader_argv(profile)
    assert "--model" in argv and "m-123" in argv


# ── gap: full precedence chain ────────────────────────────────────────────────


def test_precedence_cli_over_env(monkeypatch):
    monkeypatch.setenv("DS_GRADER_PROFILE_CORRECTNESS", "env-grader")
    resolved = resolve_grader_profile("correctness", cli_override="cli-grader")
    assert resolved["command"] == "cli-grader"


def test_precedence_env_over_config_file(monkeypatch, tmp_path):
    cfg = tmp_path / "profiles.json"
    cfg.write_text(json.dumps({"correctness": {"command": "file-grader"}}), encoding="utf-8")
    monkeypatch.setenv("DS_GRADER_PROFILE_CONFIG", str(cfg))
    monkeypatch.setenv("DS_GRADER_PROFILE_CORRECTNESS", "env-grader")
    assert resolve_grader_profile("correctness")["command"] == "env-grader"


def test_precedence_config_file_over_default(monkeypatch, tmp_path):
    cfg = tmp_path / "profiles.json"
    cfg.write_text(json.dumps({"correctness": {"command": "file-grader"}}), encoding="utf-8")
    monkeypatch.setenv("DS_GRADER_PROFILE_CONFIG", str(cfg))
    assert resolve_grader_profile("correctness")["command"] == "file-grader"


def test_stub_dominates(monkeypatch, tmp_path):
    stub = tmp_path / "stub.py"
    stub.write_text("", encoding="utf-8")
    monkeypatch.setenv("DS_GRADER_STUB", str(stub))
    resolved = resolve_grader_profile("correctness", cli_override="cli-grader")
    assert resolved["is_stub"] is True


# ── gap: fail-closed message names the exact keys ─────────────────────────────


def test_fail_closed_message_names_keys():
    with pytest.raises(UnresolvableGraderProfile) as exc:
        resolve_grader_profile("correctness", profiles={})
    msg = str(exc.value)
    assert "DS_GRADER_PROFILE_CORRECTNESS" in msg
    assert "DS_GRADER_PROFILE_CONFIG" in msg


# ── gap: inspectable role -> provider mapping ─────────────────────────────────


def test_describe_grader_selection_covers_all_roles():
    mapping = describe_grader_selection()
    assert set(mapping) == set(GRADER_ROLES)
    for role, info in mapping.items():
        assert info.get("provider_id"), f"{role} should resolve to a provider under defaults"
