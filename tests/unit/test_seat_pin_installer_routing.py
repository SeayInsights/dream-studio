"""A pinned seat (core.config.seat_providers) changes what the installers do.

`SpecialistAgentsInstaller` (md_frontmatter: gemini_cli, cursor, windsurf, aider) and
`CodexAgentsInstaller` (TOML) both consult `integrations.compiler.reviewers.
resolve_seat_assignment()` per file now: a seat pinned to a DIFFERENT provider than the
one being installed is skipped in the unfiltered "install everything" pass (so it isn't
installed twice, once under its own name and once under the pin's), but an explicit
--agents request for that exact seat is honored anyway -- naming it directly is a
stronger signal than the standing pin. A seat pinned to the SAME provider, or with no
pin at all, installs exactly as it always has, with the pin's own model/effort override
applied where it's set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import seat_providers
from integrations.compiler.reviewers import reviewer_files, seat_name_for_file
from integrations.installer.claude_code_installer import ClaudeCodeInstaller
from integrations.installer.specialist_agents_codex_target import CodexAgentsInstaller
from integrations.installer.specialist_agents_target import SpecialistAgentsInstaller

_PROJECT_LANE_YAML = """
mode: add
lanes:
  - id: a-project-specific-lane
    seat: PCI Scope
    question: >
      Does this change touch anything in the cardholder data environment?
    signature: >
      A file under payments/ or checkout/ changed with no PCI reviewer sign-off noted
      in the PR body.
    precedent: >
      Filed after an internal audit found three merged PRs touching payment capture
      with no compliance review recorded anywhere.
    measurement: >
      No automatable predicate exists for "touches CDE" without a maintained
      file-ownership map, so this is judgment rather than a detector.
    model: sonnet
    judgment: true
    why: >
      No maintained CDE file-ownership map exists yet to turn this into a detector.
"""


@pytest.fixture(autouse=True)
def isolated_ds_home(tmp_path, monkeypatch):
    """Seat-provider pins live in config.json -- isolate it from this developer's real
    ~/.dream-studio, the same way test_seat_providers.py does. A SEPARATE tmp dir from
    the installer's own project_root/home (passed explicitly by every test below),
    which is a different "home" entirely -- see the incident comment in
    test_specialist_agents_install.py on conflating the two."""
    ds_home = tmp_path / "ds-home"
    monkeypatch.setenv("HOME", str(ds_home))
    monkeypatch.setenv("USERPROFILE", str(ds_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ds_home))
    monkeypatch.delenv("DREAM_STUDIO_HOME", raising=False)


def _some_seat() -> str:
    return seat_name_for_file(reviewer_files()[0])


# ── md_frontmatter (SpecialistAgentsInstaller) ──────────────────────────────


def test_unfiltered_install_skips_a_seat_pinned_elsewhere(tmp_path):
    seat = _some_seat()
    expected_file = reviewer_files()[0].name
    seat_providers.set_seat_provider(seat, provider="codex")
    installer = SpecialistAgentsInstaller("gemini_cli", project_root=tmp_path, home=tmp_path)
    result = installer.install("execute")
    assert result["skipped"] == [{"seat": seat, "file": expected_file, "pinned_to": "codex"}]
    assert len(result["written"]) == len(reviewer_files()) - 1
    assert not (installer.target_dir / expected_file).exists()


def test_explicit_agents_request_installs_a_seat_pinned_elsewhere_anyway(tmp_path):
    seat = _some_seat()
    seat_providers.set_seat_provider(seat, provider="codex")
    installer = SpecialistAgentsInstaller(
        "gemini_cli", project_root=tmp_path, home=tmp_path, agents=[seat]
    )
    result = installer.install("execute")
    assert result["skipped"] == []
    assert len(result["written"]) == 1


def test_a_seat_pinned_to_the_same_tool_installs_normally(tmp_path):
    seat = _some_seat()
    seat_providers.set_seat_provider(seat, provider="gemini_cli")
    installer = SpecialistAgentsInstaller("gemini_cli", project_root=tmp_path, home=tmp_path)
    result = installer.install("execute")
    assert result["skipped"] == []
    assert len(result["written"]) == len(reviewer_files())


def test_a_pinned_model_override_is_applied_not_the_files_own_alias(tmp_path):
    from integrations.targets.registry import translate_model

    seat = _some_seat()
    seat_providers.set_seat_provider(seat, provider="gemini_cli", model="opus")
    installer = SpecialistAgentsInstaller(
        "gemini_cli", project_root=tmp_path, home=tmp_path, agents=[seat]
    )
    installer.install("execute")
    written = next(installer.target_dir.iterdir())
    assert f"model: {translate_model('gemini_cli', 'opus')}" in written.read_text(encoding="utf-8")


def test_an_unpinned_seat_installs_exactly_as_before(tmp_path):
    installer = SpecialistAgentsInstaller("gemini_cli", project_root=tmp_path, home=tmp_path)
    result = installer.install("execute")
    assert result["skipped"] == []
    assert len(result["written"]) == len(reviewer_files())


def test_dry_run_reports_skipped_without_writing_anything(tmp_path):
    seat = _some_seat()
    seat_providers.set_seat_provider(seat, provider="codex")
    installer = SpecialistAgentsInstaller("gemini_cli", project_root=tmp_path, home=tmp_path)
    result = installer.install("dry_run")
    assert result["skipped"] == [
        {"seat": seat, "file": reviewer_files()[0].name, "pinned_to": "codex"}
    ]
    assert not installer.target_dir.exists()


# ── TOML (CodexAgentsInstaller) ──────────────────────────────────────────


def test_codex_installer_skips_a_seat_pinned_elsewhere(tmp_path):
    seat = _some_seat()
    seat_providers.set_seat_provider(seat, provider="gemini_cli")
    installer = CodexAgentsInstaller(project_root=tmp_path, home=tmp_path)
    result = installer.install("execute")
    assert result["skipped"] == [
        {"seat": seat, "file": reviewer_files()[0].name, "pinned_to": "gemini_cli"}
    ]


def test_codex_installer_explicit_agents_honors_a_seat_pinned_elsewhere(tmp_path):
    seat = _some_seat()
    seat_providers.set_seat_provider(seat, provider="gemini_cli")
    installer = CodexAgentsInstaller(project_root=tmp_path, home=tmp_path, agents=[seat])
    result = installer.install("execute")
    assert result["skipped"] == []
    assert len(result["written"]) == 1


def test_codex_installer_applies_a_pinned_effort(tmp_path):
    seat = _some_seat()
    seat_providers.set_seat_provider(seat, provider="codex", model="opus", effort="high")
    installer = CodexAgentsInstaller(project_root=tmp_path, home=tmp_path, agents=[seat])
    installer.install("execute")
    written = next(installer.target_dir.iterdir())
    text = written.read_text(encoding="utf-8")
    assert 'model_reasoning_effort = "high"' in text


def test_codex_installer_does_not_apply_effort_from_a_pin_for_a_different_tool(tmp_path):
    """An --agents override installs a seat pinned elsewhere, but effort is tied to the
    PINNED provider's own vocabulary -- it must not leak onto a different tool's TOML."""
    seat = _some_seat()
    seat_providers.set_seat_provider(seat, provider="gemini_cli")
    installer = CodexAgentsInstaller(project_root=tmp_path, home=tmp_path, agents=[seat])
    installer.install("execute")
    written = next(installer.target_dir.iterdir())
    assert "model_reasoning_effort" not in written.read_text(encoding="utf-8")


def test_an_unpinned_seat_installs_on_codex_exactly_as_before(tmp_path):
    installer = CodexAgentsInstaller(project_root=tmp_path, home=tmp_path)
    result = installer.install("execute")
    assert result["skipped"] == []
    assert len(result["written"]) == len(reviewer_files())


# ── Claude Code's own native install path ───────────────────────────────


@pytest.fixture
def project_with_marker(tmp_path):
    root = tmp_path / "a-project"
    root.mkdir()
    (root / ".ds-review-lanes.yml").write_text(_PROJECT_LANE_YAML, encoding="utf-8")
    return root


@pytest.fixture
def config_root(tmp_path):
    cr = tmp_path / "claude_config"
    cr.mkdir()
    return cr


@pytest.fixture
def canonical_root(tmp_path):
    # No agents/ subdir -- step 5 (the canonical bench) is a no-op, which is fine:
    # these tests exercise step 5b (a project's own seat), the identical
    # resolve_seat_assignment()/set_model_alias() code path with a self-contained
    # fixture, not real canonical/agents/review-*.md content. ds-bootstrap/SKILL.md
    # still has to exist -- compile_pack() (an earlier, unrelated plan() step) raises
    # without it.
    root = tmp_path / "canonical"
    skill_dir = root / "skills" / "ds-bootstrap"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# ds-bootstrap advisory skill.", encoding="utf-8")
    return root


def test_claude_code_unfiltered_install_skips_a_project_seat_pinned_elsewhere(
    config_root, canonical_root, tmp_path, project_with_marker
):
    seat_providers.set_seat_provider("PCI Scope", provider="codex")
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=canonical_root,
        ds_home=tmp_path / "ds_home",
        git_repo_root=project_with_marker,
    )
    ops = {op.target.name: op for op in installer.plan().ops}
    assert "review-pci-scope.md" not in ops


def test_claude_code_explicit_agents_installs_a_seat_pinned_elsewhere_anyway(
    config_root, canonical_root, tmp_path, project_with_marker
):
    seat_providers.set_seat_provider("PCI Scope", provider="codex")
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=canonical_root,
        ds_home=tmp_path / "ds_home",
        git_repo_root=project_with_marker,
        agents=["PCI Scope"],
    )
    ops = {op.target.name: op for op in installer.plan().ops}
    assert "review-pci-scope.md" in ops


def test_claude_code_applies_a_pinned_model_override_verbatim(
    config_root, canonical_root, tmp_path, project_with_marker
):
    seat_providers.set_seat_provider("PCI Scope", provider="claude_code", model="haiku")
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=canonical_root,
        ds_home=tmp_path / "ds_home",
        git_repo_root=project_with_marker,
    )
    ops = {op.target.name: op for op in installer.plan().ops}
    assert "model: haiku" in ops["review-pci-scope.md"].source_content


def test_claude_code_an_unpinned_project_seat_installs_exactly_as_before(
    config_root, canonical_root, tmp_path, project_with_marker
):
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=canonical_root,
        ds_home=tmp_path / "ds_home",
        git_repo_root=project_with_marker,
    )
    ops = {op.target.name: op for op in installer.plan().ops}
    assert "review-pci-scope.md" in ops
    assert "model: sonnet" in ops["review-pci-scope.md"].source_content
