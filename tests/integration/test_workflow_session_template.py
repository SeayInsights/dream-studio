"""Integration test for {{session:<filename>}} template resolution in workflow engine."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.workflow_engine import resolve_templates  # noqa: E402


@pytest.fixture()
def session_dir(tmp_path):
    """Create a mock session directory with files."""
    sd = tmp_path / "session"
    sd.mkdir()
    (sd / "repo-context.json").write_text(
        '{"stack": {"language": "python"}, "git_hash": "abc123"}',
        encoding="utf-8",
    )
    (sd / "plan-summary.md").write_text(
        "# Plan\n- Task 1: Build API\n- Task 2: Write tests\n",
        encoding="utf-8",
    )
    return str(sd)


def test_session_template_resolves_json(session_dir):
    text = "Context: {{session:repo-context.json}}"
    result = resolve_templates(text, {}, session_dir=session_dir)
    assert "abc123" in result
    assert "python" in result


def test_session_template_resolves_markdown(session_dir):
    text = "Plan: {{session:plan-summary.md}}"
    result = resolve_templates(text, {}, session_dir=session_dir)
    assert "Build API" in result
    assert "Write tests" in result


def test_session_template_missing_file_preserved(session_dir):
    text = "Data: {{session:nonexistent.json}}"
    result = resolve_templates(text, {}, session_dir=session_dir)
    assert result == text


def test_session_template_no_session_dir():
    text = "Data: {{session:something.json}}"
    result = resolve_templates(text, {}, session_dir=None)
    assert result == text


def test_mixed_templates(session_dir):
    wf = {"nodes": {"build": {"output": "done", "status": "completed"}}}
    text = "Build: {{build.output}}, Repo: {{session:repo-context.json}}"
    result = resolve_templates(text, wf, session_dir=session_dir)
    assert "done" in result
    assert "abc123" in result


def test_session_all_files(session_dir):
    text = "All: {{session:*}}"
    result = resolve_templates(text, {}, session_dir=session_dir)
    assert "repo-context.json" in result
    assert "plan-summary.md" in result


def test_node_template_still_works():
    wf = {"nodes": {"review": {"output": "compliant", "status": "completed"}}}
    text = "Review: {{review.output}}"
    result = resolve_templates(text, wf)
    assert result == "Review: compliant"


def test_unresolved_node_preserved():
    text = "Missing: {{unknown.output}}"
    result = resolve_templates(text, {})
    assert result == text
