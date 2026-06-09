from __future__ import annotations

from pathlib import Path

import pytest

from integrations.compiler.claude_code import compile_pack


@pytest.fixture
def canonical_root(tmp_path):
    root = tmp_path / "canonical"
    skill_dir = root / "skills" / "ds-bootstrap"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# ds-bootstrap skill\nAdvisory context.", encoding="utf-8")
    (root / "events").mkdir()
    return root


def test_compile_pack_returns_correct_tool(canonical_root):
    pack = compile_pack(canonical_root)
    assert pack["tool"] == "claude_code"


def test_compile_pack_includes_skill_md(canonical_root):
    pack = compile_pack(canonical_root)
    assert "skills/ds-bootstrap/SKILL.md" in pack["files"]
    assert "ds-bootstrap" in pack["files"]["skills/ds-bootstrap/SKILL.md"]


def test_compile_pack_canonical_root_is_recorded(canonical_root):
    pack = compile_pack(canonical_root)
    assert str(canonical_root) in pack["canonical_root"]


def test_compile_pack_includes_settings_hooks(canonical_root):
    pack = compile_pack(canonical_root)
    assert isinstance(pack["settings_hooks"], list)


def test_compile_pack_is_deterministic(canonical_root):
    p1 = compile_pack(canonical_root)
    p2 = compile_pack(canonical_root)
    assert p1["files"] == p2["files"]


def test_compile_pack_raises_when_skill_md_missing(tmp_path):
    empty_root = tmp_path / "canonical"
    empty_root.mkdir()
    with pytest.raises(FileNotFoundError):
        compile_pack(empty_root)


def test_compile_pack_uses_default_canonical_when_none():
    pack = compile_pack(None)
    assert pack["tool"] == "claude_code"
    assert "skills/ds-bootstrap/SKILL.md" in pack["files"]
