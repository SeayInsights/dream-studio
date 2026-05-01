"""Tests for hooks/lib/model_selector.py — get_model_for_skill() frontmatter lookup."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.model_selector import (  # noqa: E402
    get_model_for_skill,
    _read_model_tier,
    _resolve_skill_md,
)


class TestGetModelForSkill:
    """Integration tests against the real SKILL.md files in the repo."""

    def test_opus_skill_think(self) -> None:
        assert get_model_for_skill("dream-studio:core think") == "opus"

    def test_opus_skill_secure(self) -> None:
        assert get_model_for_skill("dream-studio:quality secure") == "opus"

    def test_opus_skill_binary_scan(self) -> None:
        assert get_model_for_skill("dream-studio:security binary-scan") == "opus"

    def test_opus_skill_multi(self) -> None:
        assert get_model_for_skill("dream-studio:analyze multi") == "opus"

    def test_opus_skill_comply(self) -> None:
        assert get_model_for_skill("dream-studio:security comply") == "opus"

    def test_haiku_skill_explain(self) -> None:
        assert get_model_for_skill("dream-studio:core explain") == "haiku"

    def test_haiku_skill_recap(self) -> None:
        assert get_model_for_skill("dream-studio:core recap") == "haiku"

    def test_haiku_skill_coach(self) -> None:
        assert get_model_for_skill("dream-studio:quality coach") == "haiku"

    def test_haiku_skill_jit(self) -> None:
        assert get_model_for_skill("dream-studio:setup jit") == "haiku"

    def test_haiku_skill_handoff(self) -> None:
        assert get_model_for_skill("dream-studio:core handoff") == "haiku"

    def test_sonnet_skill_build(self) -> None:
        assert get_model_for_skill("dream-studio:core build") == "sonnet"

    def test_sonnet_skill_debug(self) -> None:
        assert get_model_for_skill("dream-studio:quality debug") == "sonnet"

    def test_sonnet_skill_plan(self) -> None:
        assert get_model_for_skill("dream-studio:core plan") == "sonnet"

    def test_sonnet_skill_review(self) -> None:
        assert get_model_for_skill("dream-studio:core review") == "sonnet"

    def test_unknown_skill_defaults_to_sonnet(self) -> None:
        assert get_model_for_skill("nonexistent-skill") == "sonnet"

    def test_empty_string_defaults_to_sonnet(self) -> None:
        assert get_model_for_skill("") == "sonnet"

    def test_custom_default(self) -> None:
        assert get_model_for_skill("nonexistent", default="haiku") == "haiku"

    def test_invalid_default_falls_back_to_sonnet(self) -> None:
        assert get_model_for_skill("nonexistent", default="gpt-4") == "sonnet"


class TestReadModelTier:
    """Unit tests for _read_model_tier using temp files."""

    def test_reads_tier_from_frontmatter(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(textwrap.dedent("""\
            ---
            name: test-skill
            model_tier: opus
            description: A test skill
            ---
            # Content
        """))
        assert _read_model_tier(skill_md) == "opus"

    def test_missing_model_tier_returns_none(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(textwrap.dedent("""\
            ---
            name: test-skill
            description: No tier declared
            ---
            # Content
        """))
        assert _read_model_tier(skill_md) is None

    def test_invalid_tier_returns_none(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(textwrap.dedent("""\
            ---
            name: test-skill
            model_tier: gpt-4-turbo
            description: Invalid tier value
            ---
            # Content
        """))
        assert _read_model_tier(skill_md) is None

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# Just markdown, no frontmatter\n")
        assert _read_model_tier(skill_md) is None

    def test_nonexistent_file_returns_none(self, tmp_path: Path) -> None:
        assert _read_model_tier(tmp_path / "nonexistent.md") is None

    def test_handles_bom(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_bytes(b"\xef\xbb\xbf---\nname: test\nmodel_tier: haiku\n---\n")
        assert _read_model_tier(skill_md) == "haiku"


class TestResolveSkillMd:
    """Tests for skill specifier resolution."""

    def test_full_specifier(self) -> None:
        result = _resolve_skill_md("dream-studio:core think")
        assert result is not None
        assert result.is_file()
        assert "think" in str(result)

    def test_without_prefix(self) -> None:
        result = _resolve_skill_md("core think")
        assert result is not None
        assert result.is_file()

    def test_mode_only(self) -> None:
        result = _resolve_skill_md("think")
        assert result is not None
        assert result.is_file()

    def test_nonexistent_returns_none(self) -> None:
        assert _resolve_skill_md("nonexistent-pack nonexistent-mode") is None
