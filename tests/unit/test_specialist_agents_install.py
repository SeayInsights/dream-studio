"""Installing the round table's reviewers onto gemini_cli and cursor.

`SpecialistAgentsInstaller` copies each compiled `canonical/agents/review-*.md` file
verbatim except for its one tool-specific line, `model:`. These tests hold that the
translation is real (the written file's model differs from the source's, and matches
what `translate_model` says it should), that nothing else in the body changes, and that
a tool declaring the wrong specialist_agent_format (or none at all) is refused rather
than silently mishandled.
"""

from __future__ import annotations

import pytest

from integrations.compiler.reviewers import AGENTS_DIR
from integrations.installer.specialist_agents_target import (
    SpecialistAgentsInstaller,
    reviewer_files,
    translate_reviewer_body,
)
from integrations.targets.registry import translate_model

MD_FRONTMATTER_TOOLS = ("gemini_cli", "cursor")


def test_reviewer_files_is_populated():
    """Guard the guard: an empty set would make every case below vacuous."""
    assert reviewer_files(), f"no review-*.md files found under {AGENTS_DIR}"


@pytest.mark.parametrize("tool_id", MD_FRONTMATTER_TOOLS)
def test_translate_reviewer_body_changes_only_the_model_line(tool_id):
    for path in reviewer_files():
        original = path.read_text(encoding="utf-8")
        translated = translate_reviewer_body(original, tool_id)

        orig_lines = original.splitlines()
        new_lines = translated.splitlines()
        assert len(orig_lines) == len(new_lines), path.name
        model_index = next(i for i, ln in enumerate(orig_lines) if ln.startswith("model: "))
        diffs = [i for i, (a, b) in enumerate(zip(orig_lines, new_lines)) if a != b]
        assert diffs == [model_index], (
            f"{path.name}: expected only the model line (index {model_index}) to"
            f" change, changed {diffs}"
        )
        assert new_lines[model_index].startswith("model: ")


@pytest.mark.parametrize("tool_id", MD_FRONTMATTER_TOOLS)
def test_translate_reviewer_body_uses_the_real_translation(tool_id):
    path = reviewer_files()[0]
    original = path.read_text(encoding="utf-8")
    original_alias = [ln for ln in original.splitlines() if ln.startswith("model: ")][
        0
    ].removeprefix("model: ")
    translated = translate_reviewer_body(original, tool_id)
    expected = translate_model(tool_id, original_alias)
    assert f"model: {expected}" in translated


def test_translate_reviewer_body_refuses_a_body_with_no_model_line():
    with pytest.raises(ValueError, match="no `model:` line"):
        translate_reviewer_body("---\nname: x\n---\nno model here", "gemini_cli")


@pytest.mark.parametrize("tool_id", MD_FRONTMATTER_TOOLS)
def test_installer_rejects_dry_run_without_writing(tool_id, tmp_path):
    # home=tmp_path is load-bearing, not decoration: cursor's scope is "user", so
    # omitting it resolves target_dir against this machine's REAL home directory --
    # exactly the isolation bug this suite must never repeat (see the incident this
    # comment is next to: an earlier version of this test file did that and the
    # "execute" test below wrote nine real files into this developer's actual
    # ~/.cursor/agents/, cleaned up by hand after the fact).
    installer = SpecialistAgentsInstaller(tool_id, project_root=tmp_path, home=tmp_path)
    result = installer.install("dry_run")
    assert result["written"] == []
    assert not installer.target_dir.exists()


@pytest.mark.parametrize("tool_id", MD_FRONTMATTER_TOOLS)
def test_dry_run_still_reports_which_files_it_would_write(tool_id, tmp_path):
    """A dry-run that reports only written: [] answers "did anything happen" (no) but
    not "what would happen" -- the actual question a dry-run exists to answer, and the
    one an operator ran --dry-run to get. Caught directly after this installer shipped:
    the real CLI's --dry-run gave a target_dir and an empty list, nothing else."""
    installer = SpecialistAgentsInstaller(tool_id, project_root=tmp_path, home=tmp_path)
    result = installer.install("dry_run")
    assert set(result["files"]) == {f.name for f in reviewer_files()}


@pytest.mark.parametrize("tool_id", MD_FRONTMATTER_TOOLS)
def test_agents_subset_installs_only_the_requested_reviewers(tool_id, tmp_path):
    installer = SpecialistAgentsInstaller(
        tool_id,
        project_root=tmp_path,
        home=tmp_path,
        agents=["Finding integrity", "review-boundary-semantics"],
    )
    result = installer.install("execute")
    assert set(result["written"]) == {
        "review-finding-integrity.md",
        "review-boundary-semantics.md",
    }
    written_files = {p.name for p in installer.target_dir.iterdir()}
    assert written_files == {"review-finding-integrity.md", "review-boundary-semantics.md"}
    all_files = {f.name for f in reviewer_files()}
    assert len(all_files) > 2, "subset test is meaningless if the full bench isn't bigger"


@pytest.mark.parametrize("tool_id", MD_FRONTMATTER_TOOLS)
def test_agents_subset_with_an_unknown_name_raises_before_writing_anything(tool_id, tmp_path):
    with pytest.raises(ValueError, match="unknown"):
        SpecialistAgentsInstaller(
            tool_id, project_root=tmp_path, home=tmp_path, agents=["Not A Real Seat"]
        )
    # The installer must not have gotten far enough to create the target directory --
    # an unknown name is refused at construction, before any file operation.
    assert not (tmp_path / ".gemini").exists()
    assert not (tmp_path / ".cursor").exists()


@pytest.mark.parametrize("tool_id", MD_FRONTMATTER_TOOLS)
def test_installer_writes_every_reviewer_with_its_model_translated(tool_id, tmp_path):
    # See the comment on test_installer_rejects_dry_run_without_writing: home=tmp_path
    # is required for every tool here, not just the ones whose scope currently needs it.
    installer = SpecialistAgentsInstaller(tool_id, project_root=tmp_path, home=tmp_path)
    result = installer.install("execute")

    files = reviewer_files()
    assert set(result["written"]) == {f.name for f in files}

    for src in files:
        original = src.read_text(encoding="utf-8")
        original_alias = [ln for ln in original.splitlines() if ln.startswith("model: ")][
            0
        ].removeprefix("model: ")
        expected_model = translate_model(tool_id, original_alias)

        written = (installer.target_dir / src.name).read_text(encoding="utf-8")
        assert f"model: {expected_model}" in written
        # Everything else -- name, description, banner, every lane's question and
        # signature, the "answer by running things" contract -- is untouched.
        assert (
            written.replace(f"model: {expected_model}", f"model: {original_alias}", 1) == original
        )


def test_installer_refuses_a_tool_with_a_different_specialist_format(tmp_path):
    with pytest.raises(ValueError, match="not 'md_frontmatter'"):
        SpecialistAgentsInstaller("codex", project_root=tmp_path, home=tmp_path)


def test_installer_refuses_a_tool_with_no_specialist_capability(tmp_path):
    with pytest.raises(ValueError, match="not 'md_frontmatter'"):
        SpecialistAgentsInstaller("aider", project_root=tmp_path, home=tmp_path)


# --------------------------------------------------------------------------
# A project's own seat installs alongside Dream Studio's bench
# --------------------------------------------------------------------------

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


@pytest.mark.parametrize("tool_id", MD_FRONTMATTER_TOOLS)
def test_an_unfiltered_install_includes_the_project_root_s_own_seat(tool_id, tmp_path):
    (tmp_path / ".ds-review-lanes.yml").write_text(_PROJECT_LANE_YAML, encoding="utf-8")

    installer = SpecialistAgentsInstaller(tool_id, project_root=tmp_path, home=tmp_path)
    result = installer.install("execute")

    assert "review-pci-scope.md" in result["written"]
    assert set(result["written"]) == {f.name for f in reviewer_files()} | {"review-pci-scope.md"}


@pytest.mark.parametrize("tool_id", MD_FRONTMATTER_TOOLS)
def test_a_project_root_with_no_marker_installs_only_the_ds_bench(tool_id, tmp_path):
    """The composition is additive, not automatic-everywhere: a project_root with no
    marker installs exactly what it always did, nothing more."""
    installer = SpecialistAgentsInstaller(tool_id, project_root=tmp_path, home=tmp_path)
    result = installer.install("execute")

    assert set(result["written"]) == {f.name for f in reviewer_files()}


@pytest.mark.parametrize("tool_id", MD_FRONTMATTER_TOOLS)
def test_agents_subset_can_name_a_project_seat_explicitly(tool_id, tmp_path):
    (tmp_path / ".ds-review-lanes.yml").write_text(_PROJECT_LANE_YAML, encoding="utf-8")

    installer = SpecialistAgentsInstaller(
        tool_id, project_root=tmp_path, home=tmp_path, agents=["PCI Scope"]
    )
    result = installer.install("execute")

    assert result["written"] == ["review-pci-scope.md"]


@pytest.mark.parametrize("tool_id", MD_FRONTMATTER_TOOLS)
def test_an_explicit_ds_only_subset_does_not_pull_in_a_project_seat(tool_id, tmp_path):
    """An explicit --agents list is a complete request, not DS-bench-plus-whatever-else
    the project happens to have -- a marker present alongside the subset must not widen
    it silently."""
    (tmp_path / ".ds-review-lanes.yml").write_text(_PROJECT_LANE_YAML, encoding="utf-8")

    installer = SpecialistAgentsInstaller(
        tool_id, project_root=tmp_path, home=tmp_path, agents=["Finding integrity"]
    )
    result = installer.install("execute")

    assert result["written"] == ["review-finding-integrity.md"]
