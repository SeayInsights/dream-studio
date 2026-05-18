"""Workstream 5c gate: ds-project skill structure and content assertions."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "canonical" / "skills" / "ds-project" / "SKILL.md"
PACKS_YAML = REPO_ROOT / "packs.yaml"

PHASE_HEADERS = [
    "Phase 1 — Discovery",
    "Phase 2 — Milestone Decomposition",
    "Phase 3 — Work Order Generation",
    "Phase 4 — Task Decomposition",
    "Phase 5 — Write Output",
]

WORK_ORDER_TYPES = [
    "ui_component",
    "ui_page",
    "api_endpoint",
    "authentication",
    "saas_feature",
    "data_pipeline",
    "game_mechanic",
    "deployment",
    "infrastructure",
    "documentation",
]


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _packs() -> dict:
    return yaml.safe_load(PACKS_YAML.read_text(encoding="utf-8"))


# ── File existence ────────────────────────────────────────────────────────────


def test_skill_md_exists():
    assert SKILL_PATH.is_file(), f"SKILL.md missing at {SKILL_PATH}"


def test_skill_path_is_readable():
    text = _skill_text()
    assert len(text) > 100, "SKILL.md is suspiciously short"


def test_modes_scope_dir_exists():
    scope_dir = REPO_ROOT / "canonical" / "skills" / "ds-project" / "modes" / "scope"
    assert scope_dir.is_dir(), "modes/scope/ directory missing — packs.yaml integrity will fail"


# ── Phase header presence ─────────────────────────────────────────────────────


@pytest.mark.parametrize("header", PHASE_HEADERS)
def test_skill_contains_phase_header(header):
    assert header in _skill_text(), f"SKILL.md missing phase header: '{header}'"


# ── Conversation rule presence ────────────────────────────────────────────────


def test_skill_contains_one_question_at_a_time_rule():
    text = _skill_text()
    assert "one question at a time" in text.lower(), (
        "SKILL.md must contain 'one question at a time' conversation rule"
    )


def test_skill_contains_no_placeholders_rule():
    text = _skill_text()
    assert "TBD" in text or "No placeholders" in text or "no placeholder" in text.lower(), (
        "SKILL.md must call out the no-placeholders rule"
    )


def test_skill_contains_scope_assessment_rule():
    text = _skill_text()
    assert "multi-subsystem" in text.lower() or "scope assessment" in text.lower(), (
        "SKILL.md must describe the scope assessment / multi-subsystem flag rule"
    )


def test_skill_contains_brownfield_check():
    text = _skill_text()
    assert "brownfield" in text.lower(), "SKILL.md must describe the brownfield check"


# ── Work order types ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("wot", WORK_ORDER_TYPES)
def test_skill_contains_work_order_type(wot):
    assert wot in _skill_text(), f"SKILL.md missing work order type: '{wot}'"


def test_skill_lists_exactly_10_work_order_types():
    text = _skill_text()
    found = [t for t in WORK_ORDER_TYPES if t in text]
    assert len(found) == 10, f"Expected 10 work order types, found {len(found)}: {found}"


# ── packs.yaml integration ────────────────────────────────────────────────────


def test_packs_yaml_includes_ds_project():
    packs = _packs()
    assert "ds-project" in packs.get("packs", {}), (
        "packs.yaml missing ds-project entry"
    )


def test_packs_yaml_ds_project_has_scope_mode():
    packs = _packs()
    ds_project = packs.get("packs", {}).get("ds-project", {})
    modes = ds_project.get("modes", [])
    assert "scope" in modes, f"ds-project modes must include 'scope', got: {modes}"


def test_packs_yaml_ds_project_skill_field():
    packs = _packs()
    ds_project = packs.get("packs", {}).get("ds-project", {})
    assert ds_project.get("skill") == "ds-project", (
        "ds-project pack must have skill: ds-project"
    )


# ── Resume mode — WS 8c-4 ────────────────────────────────────────────────────

RESUME_MODE_PATH = REPO_ROOT / "canonical" / "skills" / "ds-project" / "modes" / "resume"
RESUME_METADATA = RESUME_MODE_PATH / "metadata.yml"


def test_skill_contains_resume_mode_section():
    text = _skill_text()
    assert "Resume Mode" in text or "resume mode" in text.lower(), (
        "SKILL.md must contain a Resume Mode section"
    )


def test_resume_mode_contains_active_project_query_step():
    text = _skill_text()
    assert "active project" in text.lower(), (
        "Resume mode must describe querying for the active project"
    )


def test_resume_mode_contains_plain_english_output_rule():
    text = _skill_text()
    assert "plain English" in text or "plain english" in text.lower(), (
        "Resume mode must state plain English output rule"
    )


def test_resume_mode_contains_never_show_uuid_rule():
    text = _skill_text()
    assert "UUID" in text or "uuid" in text.lower(), (
        "Resume mode must contain 'never show UUID' rule"
    )


def test_resume_mode_contains_one_question_at_a_time_rule():
    text = _skill_text()
    # The scope mode already has this rule; resume mode re-states it
    assert "one question at a time" in text.lower() or "One question at a time" in text, (
        "Resume mode must restate 'one question at a time' rule"
    )


def test_packs_yaml_includes_resume_in_ds_project_modes():
    packs = _packs()
    ds_project = packs.get("packs", {}).get("ds-project", {})
    modes = ds_project.get("modes", [])
    assert "resume" in modes, f"ds-project modes must include 'resume', got: {modes}"


def test_resume_mode_metadata_yml_exists():
    assert RESUME_METADATA.is_file(), f"metadata.yml missing at {RESUME_METADATA}"


def test_resume_metadata_contains_start_building_trigger():
    import yaml
    data = yaml.safe_load(RESUME_METADATA.read_text(encoding="utf-8"))
    triggers = data.get("triggers", [])
    trigger_strs = [str(t) for t in triggers]
    combined = " ".join(trigger_strs)
    assert "start building" in combined, (
        f"metadata.yml must contain 'start building:' trigger. Got: {triggers}"
    )


def test_resume_metadata_contains_whats_next_trigger():
    import yaml
    data = yaml.safe_load(RESUME_METADATA.read_text(encoding="utf-8"))
    triggers = data.get("triggers", [])
    trigger_strs = [str(t) for t in triggers]
    combined = " ".join(trigger_strs)
    assert "what" in combined.lower() and "next" in combined.lower(), (
        f"metadata.yml must contain 'what's next:' trigger. Got: {triggers}"
    )
