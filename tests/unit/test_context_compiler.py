"""Tests for hooks/lib/context_compiler.py — section filtering, determinism, gotchas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.context_compiler import (  # noqa: E402
    _extract_skill_sections,
    _filter_high_gotchas,
    _parse_gotchas,
    _split_sections,
    compile_context,
)


# ---------------------------------------------------------------------------
# Section splitter
# ---------------------------------------------------------------------------


def test_split_sections_basic():
    md = "preamble\n## Steps\ndo stuff\n## Trigger\nskip me\n"
    sections = _split_sections(md)
    assert sections[0] == ("", "preamble\n")
    assert sections[1][0] == "## Steps"
    assert sections[2][0] == "## Trigger"


def test_split_sections_no_headers():
    md = "just text\nmore text\n"
    sections = _split_sections(md)
    assert len(sections) == 1
    assert sections[0][0] == ""


# ---------------------------------------------------------------------------
# Section extraction — keep/drop logic
# ---------------------------------------------------------------------------


def test_keeps_steps_and_rules():
    md = "## Steps\nstep 1\n## Rules\nrule 1\n## Trigger\ntriggered\n"
    result = _extract_skill_sections(md)
    assert "Process" in result
    assert "Rules" in result
    assert len(result) == 2


def test_drops_examples_and_trigger():
    md = "## Example Usage\nfoo\n## Trigger\nbar\n## Steps\nbaz\n"
    result = _extract_skill_sections(md)
    assert "Process" in result
    assert len(result) == 1


def test_output_section_extracted():
    md = "## Output Format\njson block\n"
    result = _extract_skill_sections(md)
    assert "Output Format" in result


def test_anti_patterns_extracted():
    md = "## Anti-patterns\ndon't do this\n"
    result = _extract_skill_sections(md)
    assert "Anti-patterns" in result


# ---------------------------------------------------------------------------
# Gotchas parsing
# ---------------------------------------------------------------------------


GOTCHAS_YAML = """\
avoid:
  - id: no-inline-debug
    severity: high
    title: "Don't debug inline"
    fix: "Use dream-studio:quality debug"
  - id: minor-style
    severity: low
    title: "Style nit"
    fix: "Ignore"
  - id: critical-security
    severity: critical
    title: "SQL injection"
    fix: "Use parameterized queries"
"""


def test_parse_gotchas_returns_all_entries():
    entries = _parse_gotchas(GOTCHAS_YAML)
    assert len(entries) == 3
    assert entries[0]["id"] == "no-inline-debug"


def test_filter_high_gotchas_excludes_low():
    entries = _parse_gotchas(GOTCHAS_YAML)
    filtered = _filter_high_gotchas(entries)
    ids = [e["id"] for e in filtered]
    assert "minor-style" not in ids
    assert "no-inline-debug" in ids
    assert "critical-security" in ids


def test_filter_high_gotchas_sorts_critical_first():
    entries = _parse_gotchas(GOTCHAS_YAML)
    filtered = _filter_high_gotchas(entries)
    assert filtered[0]["severity"] == "critical"


# ---------------------------------------------------------------------------
# Full compile — determinism
# ---------------------------------------------------------------------------


@pytest.fixture()
def skill_tree(tmp_path):
    """Create a minimal dream-studio project structure for compilation."""
    modes = tmp_path / "skills" / "core" / "modes" / "build"
    modes.mkdir(parents=True)

    skill_md = modes / "SKILL.md"
    skill_md.write_text(
        "---\nname: build\npack: core\n---\n"
        "# Build\n"
        "## Steps\n1. Read plan\n2. Execute\n"
        "## Rules\n- Commit after each task\n"
        "## Trigger\nbuild:\n"
        "## Example Usage\njust an example\n",
        encoding="utf-8",
    )

    orch = tmp_path / "skills" / "core" / "orchestration.md"
    orch.write_text(
        "# Orchestration\n"
        "## Model Selection\n| Tier | Model |\n|---|---|\n| default | sonnet |\n"
        "## Handling agent responses\nCheck signal field\n"
        "## Other stuff\nskip this\n",
        encoding="utf-8",
    )

    gotchas = modes / "gotchas.yml"
    gotchas.write_text(GOTCHAS_YAML, encoding="utf-8")

    return tmp_path


def test_compile_is_deterministic(skill_tree):
    a = compile_context("build", "core", project_root=str(skill_tree))
    b = compile_context("build", "core", project_root=str(skill_tree))
    assert a == b


def test_compile_excludes_trigger_and_examples(skill_tree):
    result = compile_context("build", "core", project_root=str(skill_tree))
    assert "Trigger" not in result
    assert "Example Usage" not in result
    assert "just an example" not in result


def test_compile_includes_kept_sections(skill_tree):
    result = compile_context("build", "core", project_root=str(skill_tree))
    assert "Read plan" in result
    assert "Commit after each task" in result


def test_compile_includes_orchestration(skill_tree):
    result = compile_context("build", "core", project_root=str(skill_tree))
    assert "Model Selection" in result
    assert "Check signal field" in result
    assert "Other stuff" not in result


def test_compile_includes_high_gotchas_only(skill_tree):
    result = compile_context("build", "core", project_root=str(skill_tree))
    assert "SQL injection" in result
    assert "Don't debug inline" in result
    assert "Style nit" not in result


def test_compile_with_repo_context(skill_tree):
    rc_path = skill_tree / "repo-context.json"
    rc_path.write_text(
        json.dumps({"stack": {"language": "python"}, "git_hash": "abc123"}),
        encoding="utf-8",
    )
    result = compile_context(
        "build", "core",
        repo_context_path=str(rc_path),
        project_root=str(skill_tree),
    )
    assert "Project Context" in result
    assert "abc123" in result


def test_compile_missing_skill_raises(skill_tree):
    with pytest.raises(FileNotFoundError):
        compile_context("nonexistent", "core", project_root=str(skill_tree))
