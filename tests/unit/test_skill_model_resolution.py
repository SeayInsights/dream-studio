"""The skill model tier has one precedence chain, and every level of it is drivable.

52 cards declared model_preference and the only reader ignored it, taking config.yml's
model_tier or the literal "sonnet". 34 modes declare a tier in both places and 11 disagree,
so which file wins is a decision worth pinning rather than leaving to whichever line of
queries.py ran last.
"""

from __future__ import annotations

import json

import pytest

from config.skill_profiles import (
    DEFAULT_TIER,
    UnknownSkillModelTier,
    mode_env_var,
    resolve_skill_model,
)

SPEC = "quality:pr-security-scan"


@pytest.fixture(autouse=True)
def _no_ambient_overrides(monkeypatch):
    """The operator's own environment does not decide these assertions."""
    for name in ("DS_SKILL_MODEL_STUB", "DS_SKILL_MODEL_CONFIG", mode_env_var(SPEC)):
        monkeypatch.delenv(name, raising=False)


def test_nothing_declared_falls_back_to_the_default():
    assert resolve_skill_model(SPEC) == {"tier": DEFAULT_TIER, "source": "default"}


def test_the_card_is_read_when_nothing_outranks_it():
    """The 18 modes with only a card were resolving to sonnet regardless of what they asked."""
    got = resolve_skill_model(SPEC, card_preference="opus")
    assert got == {"tier": "opus", "source": "card"}


def test_config_yml_outranks_the_card():
    """Deliberate: config.yml is what resolution reads today, so the card cannot re-tier it."""
    got = resolve_skill_model(SPEC, card_preference="sonnet", config_tier="opus")
    assert got == {"tier": "opus", "source": "config-yml"}


def test_a_config_file_entry_outranks_config_yml(tmp_path, monkeypatch):
    path = tmp_path / "tiers.json"
    path.write_text(json.dumps({SPEC: "haiku"}), encoding="utf-8")
    monkeypatch.setenv("DS_SKILL_MODEL_CONFIG", str(path))
    got = resolve_skill_model(SPEC, card_preference="sonnet", config_tier="opus")
    assert got["tier"] == "haiku"
    assert got["source"] == f"config-file:{SPEC}"


def test_a_config_file_default_entry_applies_to_an_unlisted_mode(tmp_path, monkeypatch):
    path = tmp_path / "tiers.json"
    path.write_text(json.dumps({"default": "haiku"}), encoding="utf-8")
    monkeypatch.setenv("DS_SKILL_MODEL_CONFIG", str(path))
    assert resolve_skill_model(SPEC)["source"] == "config-file:default"


def test_the_per_mode_env_var_outranks_the_config_file(tmp_path, monkeypatch):
    path = tmp_path / "tiers.json"
    path.write_text(json.dumps({SPEC: "haiku"}), encoding="utf-8")
    monkeypatch.setenv("DS_SKILL_MODEL_CONFIG", str(path))
    monkeypatch.setenv(mode_env_var(SPEC), "opus")
    got = resolve_skill_model(SPEC, config_tier="sonnet")
    assert got["tier"] == "opus"
    assert got["source"].startswith("env:")


def test_an_explicit_override_outranks_the_environment(monkeypatch):
    monkeypatch.setenv(mode_env_var(SPEC), "opus")
    assert resolve_skill_model(SPEC, override="haiku") == {"tier": "haiku", "source": "override"}


def test_the_stub_pins_every_mode(monkeypatch):
    """Headless and CI runs pin one tier so a matrix does not fan out across three."""
    monkeypatch.setenv("DS_SKILL_MODEL_STUB", "haiku")
    monkeypatch.setenv(mode_env_var(SPEC), "opus")
    got = resolve_skill_model(SPEC, override="opus", config_tier="opus")
    assert got == {"tier": "haiku", "source": "stub-env"}


def test_an_unrecognised_tier_is_refused_and_names_its_source(monkeypatch):
    monkeypatch.setenv(mode_env_var(SPEC), "gpt-9")
    with pytest.raises(UnknownSkillModelTier) as excinfo:
        resolve_skill_model(SPEC)
    message = str(excinfo.value)
    assert "gpt-9" in message
    assert mode_env_var(SPEC) in message, "the error does not say which key to fix"


def test_a_typo_on_a_card_is_refused_rather_than_silently_defaulted():
    with pytest.raises(UnknownSkillModelTier):
        resolve_skill_model(SPEC, card_preference="sonnett")


def test_the_env_var_name_normalises_punctuation():
    assert mode_env_var("quality:pr-security-scan") == "DS_SKILL_MODEL_QUALITY_PR_SECURITY_SCAN"
    assert mode_env_var("core:think") == "DS_SKILL_MODEL_CORE_THINK"


def test_the_registry_resolves_every_declared_mode(monkeypatch):
    """Regression pin: the live registry resolves, and cards are no longer inert."""
    from pathlib import Path

    from core.skills.queries import list_skills

    for name in ("DS_SKILL_MODEL_STUB", "DS_SKILL_MODEL_CONFIG"):
        monkeypatch.delenv(name, raising=False)

    repo_root = Path(__file__).resolve().parents[2]
    result = list_skills(source_root=repo_root, dream_studio_home=repo_root)
    skills = result["skills"]
    assert skills

    sources = {s["model_source"] for s in skills}
    assert sources <= {"config-yml", "card", "default"}
    from_card = [s for s in skills if s["model_source"] == "card"]
    assert from_card, "no mode resolves from its card, so the field is still inert"
    assert all(s["model_preference"] in ("haiku", "sonnet", "opus") for s in skills)
