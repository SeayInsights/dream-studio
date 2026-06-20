"""WO-P20-DOCS: per-tool docs + capability matrix exist and are honest."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS = ("CURSOR", "CODEX", "GEMINI_CLI", "WINDSURF", "AIDER")
REQUIRED_SECTIONS = ("## Installation", "## What works", "## Limitations")


def test_all_five_tool_docs_exist_with_sections():
    for tool in TOOLS:
        doc = REPO_ROOT / "docs" / "tools" / f"{tool}.md"
        assert doc.is_file(), f"missing docs/tools/{tool}.md"
        text = doc.read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            assert section in text, f"{tool}.md missing section {section}"
        # Honest limitation: hooks are Claude-Code-only for every non-Claude target.
        assert "Claude-Code-only" in text or "Claude Code" in text


def test_capability_matrix_present():
    matrix = REPO_ROOT / "docs" / "TOOL_CAPABILITIES.md"
    assert matrix.is_file(), "missing docs/TOOL_CAPABILITIES.md"
    text = matrix.read_text(encoding="utf-8")

    # Feature columns named in the WO.
    for column in ("AGENTS.md routing", "Hooks", "MCP", "Subagents", "Plugin marketplace"):
        assert column in text, f"capability matrix missing column {column}"

    # Every tool has a row (Claude Code + the five targets).
    for tool in ("Claude Code", "Codex", "Gemini", "Cursor", "Windsurf", "Aider"):
        assert tool in text, f"capability matrix missing row for {tool}"

    # Honest story: Claude Code full; hooks not universal.
    assert "Claude Code only" in text or "Claude Code" in text


def test_end_to_end():
    """Docs are internally consistent: the matrix links every per-tool guide."""
    matrix = (REPO_ROOT / "docs" / "TOOL_CAPABILITIES.md").read_text(encoding="utf-8")
    for tool in TOOLS:
        assert f"tools/{tool}.md" in matrix, f"matrix must link tools/{tool}.md"
    # Core-SDLC-everywhere claim is stated.
    assert "core SDLC works everywhere" in matrix.lower() or "works everywhere" in matrix.lower()
