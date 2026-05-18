"""Slice 6d: quality:audit SKILL.md + packs.yaml integrity tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_SKILL_MD = REPO_ROOT / "canonical" / "skills" / "quality" / "modes" / "audit" / "SKILL.md"
PACKS_YAML = REPO_ROOT / "packs.yaml"


def test_audit_skill_md_exists():
    assert AUDIT_SKILL_MD.is_file(), f"SKILL.md not found at {AUDIT_SKILL_MD}"


def test_audit_skill_md_contains_health_section():
    text = AUDIT_SKILL_MD.read_text(encoding="utf-8")
    assert "audit:health" in text


def test_audit_skill_md_contains_consolidate_section():
    text = AUDIT_SKILL_MD.read_text(encoding="utf-8")
    assert "audit:consolidate" in text


def test_audit_skill_md_contains_classify_before_fix_rule():
    text = AUDIT_SKILL_MD.read_text(encoding="utf-8")
    assert "classify-before-fix" in text


def test_packs_yaml_quality_includes_audit():
    packs_data = yaml.safe_load(PACKS_YAML.read_text(encoding="utf-8"))
    quality_modes = packs_data["packs"]["quality"]["modes"]
    assert "audit" in quality_modes


def test_audit_mode_dir_registered_in_quality_modes_dir():
    audit_dir = REPO_ROOT / "canonical" / "skills" / "quality" / "modes" / "audit"
    assert audit_dir.is_dir(), f"audit mode directory not found at {audit_dir}"
    packs_data = yaml.safe_load(PACKS_YAML.read_text(encoding="utf-8"))
    quality_modes = set(packs_data["packs"]["quality"]["modes"])
    mode_dirs = {d.name for d in audit_dir.parent.iterdir() if d.is_dir()}
    unlisted = mode_dirs - quality_modes
    assert not unlisted, f"Mode dirs not listed in packs.yaml: {unlisted}"
