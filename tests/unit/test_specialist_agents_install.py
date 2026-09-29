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
