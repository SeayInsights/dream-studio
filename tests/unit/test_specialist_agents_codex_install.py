"""Installing the round table's reviewers onto Codex CLI, as TOML.

Codex's specialist-agent format is structurally different from the shared markdown +
frontmatter shape Claude Code, Gemini CLI and Cursor all use (see
`test_specialist_agents_install.py` for those): a standalone TOML file per agent. These
tests hold that `codex_toml_for_reviewer` produces TOML Python's own stdlib parser
accepts (not merely text that looks like TOML), that the round-tripped content is
byte-identical to the source `.md` file it came from, and that the model line is
genuinely translated rather than carried over unchanged.
"""

from __future__ import annotations

import tomllib

import pytest

from integrations.installer.specialist_agents_codex_target import (
    CodexAgentsInstaller,
    _split_frontmatter,
    _toml_literal_multiline,
    codex_toml_for_reviewer,
    reviewer_files,
)
from integrations.targets.registry import translate_model


def test_reviewer_files_is_populated():
    assert reviewer_files()


@pytest.mark.parametrize("path", reviewer_files(), ids=lambda p: p.stem)
def test_codex_toml_parses_as_real_toml(path):
    """Proves the output with a parser, not by eye -- text that merely looks like TOML
    is exactly what a hand-rolled writer with an escaping bug would also produce."""
    body = path.read_text(encoding="utf-8")
    parsed = tomllib.loads(codex_toml_for_reviewer(body))
    assert set(parsed) == {"name", "description", "model", "developer_instructions"}


@pytest.mark.parametrize("path", reviewer_files(), ids=lambda p: p.stem)
def test_codex_toml_round_trips_the_source_content_byte_identical(path):
    body = path.read_text(encoding="utf-8")
    fields, instructions = _split_frontmatter(body)
    parsed = tomllib.loads(codex_toml_for_reviewer(body))
    assert parsed["name"] == fields["name"]
    assert parsed["description"] == fields["description"]
    assert parsed["developer_instructions"] == instructions


@pytest.mark.parametrize("path", reviewer_files(), ids=lambda p: p.stem)
def test_codex_toml_model_is_actually_translated(path):
    body = path.read_text(encoding="utf-8")
    fields, _ = _split_frontmatter(body)
    original_alias = fields["model"]
    parsed = tomllib.loads(codex_toml_for_reviewer(body))
    assert parsed["model"] == translate_model("codex", original_alias)
    assert parsed["model"] != original_alias, (
        "codex's model catalog (gpt-6-*) never collides with Dream Studio's own"
        " aliases (haiku/sonnet/opus), so an unchanged value here means translation"
        " was skipped, not that it happened to be a no-op"
    )


def test_toml_literal_multiline_refuses_content_containing_triple_quote():
    with pytest.raises(ValueError, match="cannot carry"):
        _toml_literal_multiline("some text with a literal ''' inside it")


def test_split_frontmatter_refuses_a_non_frontmatter_file():
    with pytest.raises(ValueError, match="not a"):
        _split_frontmatter("no frontmatter here at all")


def test_codex_toml_refuses_a_body_with_no_model():
    with pytest.raises(ValueError, match="no `model`"):
        codex_toml_for_reviewer("---\nname: x\ndescription: y\n---\nbody\n")


class TestCodexAgentsInstaller:
    def test_rejects_dry_run_without_writing(self, tmp_path):
        installer = CodexAgentsInstaller(project_root=tmp_path, home=tmp_path)
        result = installer.install("dry_run")
        assert result["written"] == []
        assert not installer.target_dir.exists()

    def test_writes_every_reviewer_as_valid_toml(self, tmp_path):
        installer = CodexAgentsInstaller(project_root=tmp_path, home=tmp_path)
        result = installer.install("execute")

        files = reviewer_files()
        assert set(result["written"]) == {f"{f.stem}.toml" for f in files}
        assert installer.target_dir == tmp_path / ".codex" / "agents"

        for src in files:
            written = (installer.target_dir / f"{src.stem}.toml").read_text(encoding="utf-8")
            parsed = tomllib.loads(written)
            _, instructions = _split_frontmatter(src.read_text(encoding="utf-8"))
            assert parsed["developer_instructions"] == instructions

    def test_dry_run_still_reports_which_files_it_would_write(self, tmp_path):
        installer = CodexAgentsInstaller(project_root=tmp_path, home=tmp_path)
        result = installer.install("dry_run")
        assert set(result["files"]) == {f"{f.stem}.toml" for f in reviewer_files()}

    def test_agents_subset_installs_only_the_requested_reviewer(self, tmp_path):
        installer = CodexAgentsInstaller(
            project_root=tmp_path, home=tmp_path, agents=["Finding integrity"]
        )
        result = installer.install("execute")
        assert result["written"] == ["review-finding-integrity.toml"]
        assert {p.name for p in installer.target_dir.iterdir()} == {"review-finding-integrity.toml"}

    def test_agents_subset_with_an_unknown_name_raises_before_writing_anything(self, tmp_path):
        with pytest.raises(ValueError, match="unknown"):
            CodexAgentsInstaller(project_root=tmp_path, home=tmp_path, agents=["Not A Real Seat"])
        assert not (tmp_path / ".codex").exists()
