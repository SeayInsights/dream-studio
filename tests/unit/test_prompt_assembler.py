"""Tests for hooks/lib/prompt_assembler.py — template selection, prefix identity, separator."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.prompt_assembler import (  # noqa: E402
    SEPARATOR,
    _build_dynamic_content,
    _read_template,
    assemble_prompt,
)


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------


def test_read_valid_templates():
    for name in ("implementer", "reviewer", "auditor", "explorer"):
        text = _read_template(name)
        assert "{{STATIC_CONTEXT}}" in text
        assert "{{DYNAMIC_CONTENT}}" in text


def test_read_invalid_template_raises():
    with pytest.raises(ValueError, match="Unknown template"):
        _read_template("hacker")


# ---------------------------------------------------------------------------
# Dynamic content builder
# ---------------------------------------------------------------------------


def test_dynamic_from_text():
    result = _build_dynamic_content(task_text="Build API")
    assert result == "Build API"


def test_dynamic_from_file(tmp_path):
    f = tmp_path / "task.md"
    f.write_text("# Task\nDo the thing", encoding="utf-8")
    result = _build_dynamic_content(task_file=str(f))
    assert "Do the thing" in result


def test_dynamic_with_decisions():
    result = _build_dynamic_content(task_text="Build it", decisions="Use Redis")
    assert "Build it" in result
    assert "### Decisions" in result
    assert "Use Redis" in result


def test_dynamic_empty():
    result = _build_dynamic_content()
    assert result == "(no task provided)"


# ---------------------------------------------------------------------------
# Full assembly
# ---------------------------------------------------------------------------


@pytest.fixture()
def static_context_file(tmp_path):
    path = tmp_path / "compiled.md"
    path.write_text(
        "# build — Compiled Context\n\n## Rules\n- Commit after each task\n",
        encoding="utf-8",
    )
    return path


def test_assemble_implementer(static_context_file):
    result = assemble_prompt(
        "implementer",
        str(static_context_file),
        task_text="Build the endpoint",
    )
    assert "Implementer Agent" in result
    assert "Compiled Context" in result
    assert "Build the endpoint" in result
    assert SEPARATOR in result


def test_assemble_reviewer(static_context_file):
    result = assemble_prompt(
        "reviewer",
        str(static_context_file),
        task_text="Check compliance",
    )
    assert "Reviewer Agent" in result
    assert "Check compliance" in result


def test_assemble_auditor(static_context_file):
    result = assemble_prompt(
        "auditor",
        str(static_context_file),
        task_text="Audit security",
    )
    assert "Auditor Agent" in result
    assert "Audit security" in result


def test_assemble_explorer(static_context_file):
    result = assemble_prompt(
        "explorer",
        str(static_context_file),
        task_text="Where is X?",
    )
    assert "Explorer Agent" in result
    assert "Where is X?" in result


# ---------------------------------------------------------------------------
# Cache optimization — byte-identical prefix
# ---------------------------------------------------------------------------


def test_static_prefix_identical_across_tasks(static_context_file):
    a = assemble_prompt(
        "implementer",
        str(static_context_file),
        task_text="Task A: build endpoints",
    )
    b = assemble_prompt(
        "implementer",
        str(static_context_file),
        task_text="Task B: build models",
    )
    prefix_a = a.split(SEPARATOR)[0]
    prefix_b = b.split(SEPARATOR)[0]
    assert prefix_a == prefix_b

    suffix_a = a.split(SEPARATOR)[1]
    suffix_b = b.split(SEPARATOR)[1]
    assert suffix_a != suffix_b


def test_missing_static_context_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        assemble_prompt("implementer", str(tmp_path / "nope.md"), task_text="x")
