"""Unit tests for scripts/generate_routing.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from generate_routing import (  # noqa: E402
    BEGIN_SENTINEL,
    END_SENTINEL,
    collect_skills,
    generate_routing_block,
    update_claude_md,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skill(tmp_path: Path, name: str, pack: str, triggers: list[str], description: str = "") -> Path:
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True)
    desc = description or f"Does {name} things. Trigger on {', '.join(f'`{t}`' for t in triggers)}."
    triggers_yaml = "[" + ", ".join(f'"{t}"' for t in triggers) + "]"
    (skill_dir / "metadata.yml").write_text(
        f"name: {name}\npack: {pack}\ntriggers: {triggers_yaml}\ndescription: \"{desc}\"\n",
        encoding="utf-8",
    )
    return skill_dir


def _make_claude_md(tmp_path: Path, inner: str = "placeholder content") -> Path:
    path = tmp_path / "CLAUDE.md"
    path.write_text(
        f"# Header\n\n{BEGIN_SENTINEL}\n{inner}\n{END_SENTINEL}\n\n## Footer\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_generates_table_from_triggers(tmp_path: Path) -> None:
    _make_skill(tmp_path, "build", "core", ["build:", "execute plan:"])
    _make_skill(tmp_path, "plan", "core", ["plan:", "/plan"])
    skills = collect_skills(tmp_path / "skills")
    assert len(skills) == 2
    block = generate_routing_block(skills)
    assert "build:" in block
    assert "plan:" in block
    assert "dream-studio:build" in block
    assert "dream-studio:plan" in block


def test_falls_back_to_description_parsing(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "debug"
    skill_dir.mkdir(parents=True)
    (skill_dir / "metadata.yml").write_text(
        'name: debug\npack: quality\ntriggers: []\n'
        'description: "Systematic debugging. Trigger on `debug:`, `diagnose:`."',
        encoding="utf-8",
    )
    skills = collect_skills(tmp_path / "skills")
    assert len(skills) == 1
    assert "debug:" in skills[0]["triggers"]


def test_skips_skill_without_metadata(tmp_path: Path) -> None:
    (tmp_path / "skills" / "orphan").mkdir(parents=True)
    # No metadata.yml — should be silently skipped
    _make_skill(tmp_path, "build", "core", ["build:"])
    skills = collect_skills(tmp_path / "skills")
    names = [s["name"] for s in skills]
    assert "orphan" not in names
    assert "build" in names


def test_idempotent(tmp_path: Path) -> None:
    _make_skill(tmp_path, "build", "core", ["build:"])
    claude_md = _make_claude_md(tmp_path)

    update_claude_md(claude_md, tmp_path / "skills")
    text_after_first = claude_md.read_text(encoding="utf-8")

    update_claude_md(claude_md, tmp_path / "skills")
    text_after_second = claude_md.read_text(encoding="utf-8")

    assert text_after_first == text_after_second


def test_preserves_content_outside_sentinels(tmp_path: Path) -> None:
    _make_skill(tmp_path, "build", "core", ["build:"])
    header = "# My Header\n\nSome intro prose.\n\n"
    footer = "\n\n## Other Section\nOther content here.\n"
    path = tmp_path / "CLAUDE.md"
    path.write_text(
        f"{header}{BEGIN_SENTINEL}\nold content\n{END_SENTINEL}{footer}",
        encoding="utf-8",
    )

    update_claude_md(path, tmp_path / "skills")
    result = path.read_text(encoding="utf-8")

    assert result.startswith(header)
    assert result.endswith(footer)
    assert "old content" not in result
    assert "dream-studio:build" in result
