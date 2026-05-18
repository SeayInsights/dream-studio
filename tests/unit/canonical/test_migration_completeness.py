"""Workstream 1 gate: canonical/ migration completeness assertions."""
from __future__ import annotations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL = REPO_ROOT / "canonical"

MOVED_SKILL_PACKS = ["core", "quality", "security", "analyze", "domains", "setup", "workflow"]


def test_moved_packs_in_canonical_skills():
    for pack in MOVED_SKILL_PACKS:
        dest = CANONICAL / "skills" / pack
        assert dest.is_dir(), f"canonical/skills/{pack}/ missing after migration"


def test_agents_in_canonical():
    assert (CANONICAL / "agents").is_dir(), "canonical/agents/ missing after migration"


def test_workflows_in_canonical():
    assert (CANONICAL / "workflows").is_dir(), "canonical/workflows/ missing after migration"


def test_career_stays_in_skills():
    assert (REPO_ROOT / "skills" / "career").is_dir(), (
        "skills/career/ must not be moved — has external dependency"
    )


def test_career_skill_md_has_dependency_notice():
    skill_md = REPO_ROOT / "skills" / "career" / "SKILL.md"
    assert skill_md.is_file(), "skills/career/SKILL.md missing"
    content = skill_md.read_text(encoding="utf-8")
    assert "EXTERNAL DEPENDENCY NOTICE" in content, (
        "skills/career/SKILL.md missing dependency notice"
    )
    assert "career_studio_path" in content, (
        "skills/career/SKILL.md notice must mention career_studio_path"
    )


def test_old_skill_packs_removed_from_skills():
    for pack in MOVED_SKILL_PACKS:
        old_path = REPO_ROOT / "skills" / pack
        assert not old_path.exists(), (
            f"skills/{pack}/ should not exist after migration (moved to canonical/skills/{pack}/)"
        )


def test_old_agents_dir_removed():
    assert not (REPO_ROOT / "agents").exists(), (
        "agents/ should not exist at repo root after migration (moved to canonical/agents/)"
    )


def test_old_workflows_dir_removed():
    assert not (REPO_ROOT / "workflows").exists(), (
        "workflows/ should not exist at repo root after migration (moved to canonical/workflows/)"
    )


def test_canonical_skills_contains_existing_bootstrap():
    assert (CANONICAL / "skills" / "ds-bootstrap" / "SKILL.md").is_file(), (
        "canonical/skills/ds-bootstrap/SKILL.md must still exist after migration"
    )
