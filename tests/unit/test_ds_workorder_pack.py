"""A6.1 — ds-workorder skill pack: 5 modes load via core.skills.invocation.

Each mode wraps a function in core.work_orders.*. These tests verify that
``load_skill_content`` resolves each mode's SKILL.md and that
``packs.yaml`` registers the pack with all five modes. The actual
wrapped-function call paths are exercised by their own extraction tests
(``test_work_order_start_extraction.py``, ``test_work_order_close_extraction.py``,
etc.); this file pins the pack's existence and shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_NAME = "ds-workorder"
EXPECTED_MODES = ("start", "execute", "close", "block", "status")


@pytest.fixture(scope="module")
def packs_data() -> dict:
    import yaml

    return yaml.safe_load((REPO_ROOT / "packs.yaml").read_text(encoding="utf-8"))


def test_pack_registered_in_packs_yaml(packs_data: dict) -> None:
    packs = packs_data.get("packs", {})
    assert PACK_NAME in packs, f"{PACK_NAME!r} missing from packs.yaml"
    cfg = packs[PACK_NAME]
    assert cfg.get("skill") == PACK_NAME
    assert set(cfg.get("modes", [])) == set(
        EXPECTED_MODES
    ), f"packs.yaml modes for {PACK_NAME} do not match expected"
    assert "description" in cfg and cfg["description"]


def test_pack_level_skill_md_exists() -> None:
    pack_skill = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "SKILL.md"
    assert pack_skill.is_file(), f"{pack_skill} missing"
    content = pack_skill.read_text(encoding="utf-8")
    # Pack-level dispatch table must reference every mode.
    for mode in EXPECTED_MODES:
        assert mode in content, f"pack SKILL.md does not mention mode {mode!r}"


@pytest.mark.parametrize("mode", EXPECTED_MODES)
def test_mode_files_exist(mode: str) -> None:
    mode_dir = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "modes" / mode
    assert (mode_dir / "SKILL.md").is_file(), f"{mode}/SKILL.md missing"
    assert (mode_dir / "metadata.yml").is_file(), f"{mode}/metadata.yml missing"


@pytest.mark.parametrize("mode", EXPECTED_MODES)
def test_mode_metadata_has_triggers_and_token_estimate(mode: str) -> None:
    import yaml

    metadata_path = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "modes" / mode / "metadata.yml"
    data = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    triggers = data.get("triggers", [])
    assert triggers and all(
        isinstance(t, str) and t.endswith(":") for t in triggers
    ), f"{mode}/metadata.yml triggers must be non-empty 'keyword:' strings"
    estimated = data.get("estimated_tokens")
    assert (
        isinstance(estimated, int) and estimated > 0
    ), f"{mode}/metadata.yml must include positive integer estimated_tokens"


@pytest.mark.parametrize("mode", EXPECTED_MODES)
def test_load_skill_content_resolves_each_mode(mode: str) -> None:
    """``load_skill_content`` is the A2.4 function the workflow runner
    (A3) and skill-invoke handler (A2.4) both call. Each new mode must
    be loadable through that path."""

    from core.skills.invocation import load_skill_content

    specifier = f"{PACK_NAME}:{mode}"
    result = load_skill_content(specifier=specifier, source_root=REPO_ROOT)
    assert result["ok"] is True, f"load_skill_content failed for {specifier}: {result.get('error')}"
    assert result["pack"] == PACK_NAME
    assert result["mode"] == mode
    assert result["skill_content"], f"{specifier} SKILL.md is empty"


@pytest.mark.parametrize("mode", EXPECTED_MODES)
def test_mode_skill_md_names_a_core_function(mode: str) -> None:
    """AI-presents-from-database discipline: each mode's SKILL.md must
    name the specific ``core.work_orders.*`` function it wraps."""

    skill_md = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "modes" / mode / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    # Each mode must reference a function in core.work_orders.* by name.
    assert "core.work_orders" in content, (
        f"{mode}/SKILL.md does not reference a core.work_orders.* function — "
        f"AI-presents-from-database discipline requires every state-surfacing "
        f"instruction to name the function being called."
    )


def test_no_legacy_cli_commands_in_pack_skill_md() -> None:
    """A6 packs must apply the AI-presents-from-database discipline:
    no ``py -m interfaces.cli.ds`` invocations as user-facing instructions
    in the pack-level SKILL.md."""

    pack_skill = REPO_ROOT / "canonical" / "skills" / PACK_NAME / "SKILL.md"
    content = pack_skill.read_text(encoding="utf-8")
    assert "py -m interfaces.cli.ds" not in content, (
        f"{PACK_NAME}/SKILL.md must not contain `py -m interfaces.cli.ds` — "
        f"the AI calls the function directly."
    )
