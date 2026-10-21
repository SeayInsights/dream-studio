"""The installer ships a skill's support trees, and the doctor compares them.

WHY (issue #895 item 7, follow-up). plugin_dist shipped `templates/security/` inside the
ds-security skill directory, but the installer (`ds integrate install`, which `ds
self-install` runs from the installed app) copied canonical/skills/<pack>/ only. The
security modes say `<skill-dir>/templates/security/...` and "never substitute a
repository-relative path when the skill is installed", so on that channel they pointed at
files that did not exist. Both channels now read ONE registry (SKILL_SUPPORT_TREES), and the
doctor's skill-freshness comparison includes the same trees: without that, a correct install
would read as drifted and a missing script would read as fresh.

The end-to-end proof from an installed wheel is in
tests/unit/test_wheel_runs_without_checkout.py; these tests hold the mechanism.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.health.doctor_skill_sync import _check_skill_freshness, _support_trees
from integrations.installer.claude_code import ClaudeCodeInstaller
from integrations.installer.claude_code_fileops import (
    SKILL_SUPPORT_TREES,
    _collect_skill_dir_ops,
)
from integrations.marketplace import plugin_dist

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE = REPO_ROOT / "templates" / "security"


@pytest.fixture()
def installed(tmp_path: Path):
    config_root = tmp_path / "claude_config"
    config_root.mkdir()
    ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=REPO_ROOT / "canonical",
        ds_home=tmp_path / "ds_home",
    ).install("execute")
    return config_root


def _source_files() -> set[str]:
    return {
        p.relative_to(SOURCE).as_posix()
        for p in SOURCE.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo")
    }


def test_one_registry_serves_both_channels():
    assert plugin_dist.SKILL_SUPPORT_TREES is SKILL_SUPPORT_TREES
    assert SKILL_SUPPORT_TREES["ds-security"] == (("templates/security", "templates/security"),)


def test_the_installer_writes_every_support_file_under_the_skill(installed: Path):
    shipped = {
        p.relative_to(installed / "skills" / "ds-security" / "templates" / "security").as_posix()
        for p in (installed / "skills" / "ds-security" / "templates" / "security").rglob("*")
        if p.is_file()
    }
    assert shipped == _source_files()


def test_only_the_registered_skill_gets_a_templates_tree(installed: Path):
    for skill in (installed / "skills").iterdir():
        if skill.name != "ds-security":
            assert not (skill / "templates" / "security").exists(), skill.name


def test_the_installed_scripts_are_text_with_the_source_content(installed: Path):
    rel = "etl/parse_binary.py"
    got = (installed / "skills/ds-security/templates/security" / rel).read_bytes()
    assert got.replace(b"\r\n", b"\n") == (SOURCE / rel).read_bytes().replace(b"\r\n", b"\n")


def test_a_fresh_install_compares_clean_in_the_doctor(installed: Path):
    assert (
        _check_skill_freshness(
            REPO_ROOT / "canonical" / "skills", installed / "skills", ["ds-security"]
        )
        == []
    )


def test_an_edited_installed_script_is_drift(installed: Path):
    target = installed / "skills/ds-security/templates/security/etl/parse_binary.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    assert _check_skill_freshness(
        REPO_ROOT / "canonical" / "skills", installed / "skills", ["ds-security"]
    ) == ["ds-security"]


def test_a_missing_installed_script_is_drift(installed: Path):
    (installed / "skills/ds-security/templates/security/etl/scan_coverage.py").unlink()
    assert _check_skill_freshness(
        REPO_ROOT / "canonical" / "skills", installed / "skills", ["ds-security"]
    ) == ["ds-security"]


def test_an_extra_installed_file_in_the_tree_is_drift(installed: Path):
    (installed / "skills/ds-security/templates/security/etl/stray.py").write_text(
        "x = 1\n", encoding="utf-8"
    )
    assert _check_skill_freshness(
        REPO_ROOT / "canonical" / "skills", installed / "skills", ["ds-security"]
    ) == ["ds-security"]


def test_other_skills_compare_as_before(installed: Path):
    ids = ["ds-core", "ds-analyze", "ds-quality"]
    assert (
        _check_skill_freshness(REPO_ROOT / "canonical" / "skills", installed / "skills", ids) == []
    )


def test_the_doctor_leaves_out_a_support_tree_the_source_root_lacks(tmp_path: Path):
    assert _support_trees("ds-security", tmp_path) == ()
    assert _support_trees("ds-security", REPO_ROOT) == ((SOURCE, "templates/security"),)
    assert _support_trees("ds-core", REPO_ROOT) == ()


def test_a_source_root_that_names_the_skill_without_its_tree_is_refused(tmp_path: Path):
    skill_dir = tmp_path / "canonical" / "skills" / "security"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# security\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="templates/security"):
        _collect_skill_dir_ops(
            skill_dir, tmp_path / "out", "ds-security", tmp_path / "bk", repo_root=tmp_path
        )
    # without a repo root nothing outside the skill directory is asked for
    assert _collect_skill_dir_ops(skill_dir, tmp_path / "out", "ds-security", tmp_path / "bk")
