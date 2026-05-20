"""WS 8a-2 — CLAUDE.md enforcement language compiler tests.

Tests that compile_pack() generates a CLAUDE.md whose first section
is the MANDATORY OPERATING CONSTRAINTS enforcement block.
No live config writes; all assertions are against the compiled string.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.compiler.claude_code import _ENFORCEMENT_BLOCK, _build_claude_md, compile_pack

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── enforcement block content ─────────────────────────────────────────────────


def test_enforcement_block_contains_mandatory_heading() -> None:
    assert "MANDATORY OPERATING CONSTRAINTS" in _ENFORCEMENT_BLOCK


def test_enforcement_block_contains_start_work_order_function() -> None:
    assert "start_work_order" in _ENFORCEMENT_BLOCK


def test_enforcement_block_contains_close_work_order_function() -> None:
    assert "close_work_order" in _ENFORCEMENT_BLOCK


def test_enforcement_block_contains_module_boundary_reference() -> None:
    assert "module_boundary" in _ENFORCEMENT_BLOCK


def test_enforcement_block_contains_get_next_work_order_function() -> None:
    assert "get_next_work_order" in _ENFORCEMENT_BLOCK


# ── _build_claude_md ──────────────────────────────────────────────────────────


def test_build_claude_md_starts_with_enforcement_block(tmp_path: Path) -> None:
    """Generated CLAUDE.md must begin with the enforcement block."""
    projection = tmp_path / "CLAUDE.md"
    projection.write_text("# Adapter Projection\nsome content\n")
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text("schema_version: 2\npacks: {}\n")
    result = _build_claude_md(projection, tmp_path, packs_yaml)
    assert result.startswith("# DREAM STUDIO — MANDATORY OPERATING CONSTRAINTS")


def test_build_claude_md_enforcement_appears_before_projection(tmp_path: Path) -> None:
    """Enforcement block precedes adapter projection content."""
    marker = "# ADAPTER CONTENT SENTINEL"
    projection = tmp_path / "CLAUDE.md"
    projection.write_text(f"{marker}\n")
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text("schema_version: 2\npacks: {}\n")
    result = _build_claude_md(projection, tmp_path, packs_yaml)
    enforcement_pos = result.index("MANDATORY OPERATING CONSTRAINTS")
    projection_pos = result.index(marker)
    assert enforcement_pos < projection_pos


def test_build_claude_md_missing_projection_still_returns_enforcement(tmp_path: Path) -> None:
    """If adapter projection file is missing, still returns enforcement block."""
    missing = tmp_path / "no-such-file.md"
    packs_yaml = tmp_path / "packs.yaml"
    packs_yaml.write_text("schema_version: 2\npacks: {}\n")
    result = _build_claude_md(missing, tmp_path, packs_yaml)
    assert "MANDATORY OPERATING CONSTRAINTS" in result


# ── compile_pack output ───────────────────────────────────────────────────────


def test_compiled_pack_includes_claude_md_key() -> None:
    pack = compile_pack()
    assert "CLAUDE.md" in pack["files"]


def test_compiled_claude_md_contains_mandatory_section() -> None:
    pack = compile_pack()
    claude_md = pack["files"]["CLAUDE.md"]
    assert "MANDATORY OPERATING CONSTRAINTS" in claude_md


def test_compiled_claude_md_mandatory_section_is_first() -> None:
    """MANDATORY OPERATING CONSTRAINTS must appear before any other heading."""
    pack = compile_pack()
    claude_md = pack["files"]["CLAUDE.md"]
    mandatory_pos = claude_md.index("MANDATORY OPERATING CONSTRAINTS")
    # Any content before it should only be the opening comment markers (#)
    preamble = claude_md[:mandatory_pos]
    assert preamble.strip().startswith("#"), (
        f"Expected enforcement block to be at the very top. " f"Preamble was: {preamble!r}"
    )


def test_compiled_claude_md_contains_start_work_order_function() -> None:
    pack = compile_pack()
    assert "start_work_order" in pack["files"]["CLAUDE.md"]


def test_compiled_claude_md_contains_close_work_order_function() -> None:
    pack = compile_pack()
    assert "close_work_order" in pack["files"]["CLAUDE.md"]


def test_compiled_claude_md_contains_module_boundary_reference() -> None:
    pack = compile_pack()
    assert "module_boundary" in pack["files"]["CLAUDE.md"]


def test_compiled_claude_md_contains_get_next_work_order_function() -> None:
    pack = compile_pack()
    assert "get_next_work_order" in pack["files"]["CLAUDE.md"]


# ── WS 8b-4: DB-based project tracking ───────────────────────────────────────


def test_compiled_claude_md_does_not_contain_marker_file_reference() -> None:
    pack = compile_pack()
    assert ".dream-studio-project" not in pack["files"]["CLAUDE.md"]


def test_compiled_claude_md_contains_set_active_project_function() -> None:
    pack = compile_pack()
    assert "set_active_project" in pack["files"]["CLAUDE.md"]


def test_compiled_claude_md_contains_get_project_list_function() -> None:
    pack = compile_pack()
    assert "get_project_list" in pack["files"]["CLAUDE.md"]
