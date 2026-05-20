"""Prereq A/B/C gate tests — website/fullstack pack elevation, setup registration, pr-security-scan rename."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKS_YAML = REPO_ROOT / "packs.yaml"


def _load_packs() -> dict:
    return yaml.safe_load(PACKS_YAML.read_text(encoding="utf-8"))


def _skill_md(pack: str, mode: str) -> Path:
    data = _load_packs()
    pack_info = data["packs"][pack]
    skill_path = pack_info.get("skill_path")
    if skill_path:
        return REPO_ROOT / skill_path / "modes" / mode / "SKILL.md"
    return REPO_ROOT / "canonical" / "skills" / pack / "modes" / mode / "SKILL.md"


# ── PREREQ A: website and fullstack path resolution ───────────────────────────


def test_website_discover_resolves_to_correct_skill_md():
    expected = REPO_ROOT / "canonical/skills/domains/modes/website/modes/discover/SKILL.md"
    assert _skill_md("website", "discover") == expected
    assert expected.is_file(), f"SKILL.md not found at {expected}"


def test_website_critique_resolves_to_correct_skill_md():
    expected = REPO_ROOT / "canonical/skills/domains/modes/website/modes/critique/SKILL.md"
    assert _skill_md("website", "critique") == expected
    assert expected.is_file()


def test_fullstack_frontend_resolves_to_correct_skill_md():
    expected = REPO_ROOT / "canonical/skills/domains/modes/fullstack/modes/frontend/SKILL.md"
    assert _skill_md("fullstack", "frontend") == expected
    assert expected.is_file()


def test_fullstack_backend_resolves_to_correct_skill_md():
    expected = REPO_ROOT / "canonical/skills/domains/modes/fullstack/modes/backend/SKILL.md"
    assert _skill_md("fullstack", "backend") == expected
    assert expected.is_file()


def test_fullstack_integrate_resolves_to_correct_skill_md():
    expected = REPO_ROOT / "canonical/skills/domains/modes/fullstack/modes/integrate/SKILL.md"
    assert _skill_md("fullstack", "integrate") == expected
    assert expected.is_file()


# ── PREREQ A: ds skill invoke and list ───────────────────────────────────────


def test_skill_invoke_website_discover_exits_0(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from interfaces.cli.ds import main

    rc = main(["skill", "invoke", "website:discover"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Skill: website:discover" in out
    assert "Invocation recorded." in out


def test_skill_invoke_fullstack_backend_exits_0(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from interfaces.cli.ds import main

    rc = main(["skill", "invoke", "fullstack:backend"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Skill: fullstack:backend" in out
    assert "Invocation recorded." in out


def test_skill_list_shows_website_modes(capsys):
    from interfaces.cli.ds import main

    rc = main(["skill", "list"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    specifiers = {s["specifier"] for s in data["skills"]}
    assert "website:discover" in specifiers
    assert "website:critique" in specifiers
    assert "website:page" in specifiers


def test_skill_list_shows_fullstack_modes(capsys):
    from interfaces.cli.ds import main

    rc = main(["skill", "list"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    specifiers = {s["specifier"] for s in data["skills"]}
    assert "fullstack:frontend" in specifiers
    assert "fullstack:backend" in specifiers
    assert "fullstack:integrate" in specifiers


# ── PREREQ B: setup pack registration ────────────────────────────────────────


def test_setup_wizard_resolves_to_correct_skill_md():
    expected = REPO_ROOT / "canonical/skills/setup/modes/wizard/SKILL.md"
    assert _skill_md("setup", "wizard") == expected
    assert expected.is_file()


def test_setup_status_resolves_to_correct_skill_md():
    expected = REPO_ROOT / "canonical/skills/setup/modes/status/SKILL.md"
    assert _skill_md("setup", "status") == expected
    assert expected.is_file()


def test_setup_jit_resolves_to_correct_skill_md():
    expected = REPO_ROOT / "canonical/skills/setup/modes/jit/SKILL.md"
    assert _skill_md("setup", "jit") == expected
    assert expected.is_file()


# ── PREREQ C: quality:secure rename + fullstack:integrate depth ───────────────


def test_quality_pr_security_scan_resolves_correctly():
    expected = REPO_ROOT / "canonical/skills/quality/modes/pr-security-scan/SKILL.md"
    assert _skill_md("quality", "pr-security-scan") == expected
    assert expected.is_file()


def test_quality_secure_directory_removed():
    removed = REPO_ROOT / "canonical/skills/quality/modes/secure"
    assert (
        not removed.exists()
    ), "quality/modes/secure/ must not exist after rename to pr-security-scan"


def test_fullstack_integrate_skill_md_at_least_120_lines():
    path = REPO_ROOT / "canonical/skills/domains/modes/fullstack/modes/integrate/SKILL.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 120, f"integrate SKILL.md has {len(lines)} lines; expected ≥120"


def test_fullstack_integrate_contains_partial_failure_section():
    path = REPO_ROOT / "canonical/skills/domains/modes/fullstack/modes/integrate/SKILL.md"
    content = path.read_text(encoding="utf-8")
    assert (
        "Partial Integration Failure" in content or "partial integration failure" in content.lower()
    )


def test_fullstack_integrate_contains_schema_migration_section():
    path = REPO_ROOT / "canonical/skills/domains/modes/fullstack/modes/integrate/SKILL.md"
    content = path.read_text(encoding="utf-8")
    assert "Schema Migration" in content or "schema migration" in content.lower()


def test_packs_yaml_quality_modes_contains_pr_security_scan():
    data = _load_packs()
    assert "pr-security-scan" in data["packs"]["quality"]["modes"]


def test_packs_yaml_quality_modes_does_not_contain_secure():
    data = _load_packs()
    assert "secure" not in data["packs"]["quality"]["modes"]
