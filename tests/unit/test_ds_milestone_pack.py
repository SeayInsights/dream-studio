"""A6.2 — ds-milestone skill pack: 2 modes load via core.skills.invocation.

Same shape as ``test_ds_workorder_pack.py``: pins pack-existence and the
AI-presents-from-database discipline. Wrapped-function behaviour is
covered by ``test_milestone_close_extraction.py`` and
``test_milestone_close.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_NAME = "ds-milestone"
EXPECTED_MODES = ("status", "close")


@pytest.fixture(scope="module")
def packs_data() -> dict:
    import yaml

    return yaml.safe_load((REPO_ROOT / "packs.yaml").read_text(encoding="utf-8"))


def test_pack_registered_in_packs_yaml(packs_data: dict) -> None:
    packs = packs_data.get("packs", {})
    assert PACK_NAME in packs, f"{PACK_NAME!r} missing from packs.yaml"
    cfg = packs[PACK_NAME]
    assert cfg.get("skill") == PACK_NAME
    assert set(cfg.get("modes", [])) == set(EXPECTED_MODES)
    assert "description" in cfg and cfg["description"]


def test_pack_level_skill_md_exists() -> None:
    pack_skill = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "SKILL.md"
    assert pack_skill.is_file()
    content = pack_skill.read_text(encoding="utf-8")
    for mode in EXPECTED_MODES:
        assert mode in content


@pytest.mark.parametrize("mode", EXPECTED_MODES)
def test_mode_files_exist(mode: str) -> None:
    mode_dir = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "modes" / mode
    assert (mode_dir / "SKILL.md").is_file()
    assert (mode_dir / "metadata.yml").is_file()


@pytest.mark.parametrize("mode", EXPECTED_MODES)
def test_mode_metadata_has_triggers_and_token_estimate(mode: str) -> None:
    import yaml

    metadata_path = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "modes" / mode / "metadata.yml"
    data = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    triggers = data.get("triggers", [])
    assert triggers and all(isinstance(t, str) and t.endswith(":") for t in triggers)
    assert isinstance(data.get("estimated_tokens"), int) and data["estimated_tokens"] > 0


@pytest.mark.parametrize("mode", EXPECTED_MODES)
def test_load_skill_content_resolves_each_mode(mode: str) -> None:
    from core.skills.invocation import load_skill_content

    specifier = f"{PACK_NAME}:{mode}"
    result = load_skill_content(specifier=specifier, source_root=REPO_ROOT)
    assert result["ok"] is True, f"{specifier} failed: {result.get('error')}"
    assert result["pack"] == PACK_NAME
    assert result["mode"] == mode
    assert result["skill_content"]


@pytest.mark.parametrize("mode", EXPECTED_MODES)
def test_mode_skill_md_names_a_core_function(mode: str) -> None:
    """AI-presents-from-database discipline: each mode's SKILL.md must
    name the specific ``core.milestones.*`` function it wraps."""

    skill_md = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "modes" / mode / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    assert "core.milestones" in content, (
        f"{mode}/SKILL.md does not reference a core.milestones.* function — "
        f"AI-presents-from-database discipline requires it."
    )


def test_no_legacy_cli_commands_in_pack_skill_md() -> None:
    pack_skill = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "SKILL.md"
    content = pack_skill.read_text(encoding="utf-8")
    assert "py -m interfaces.cli.ds" not in content
