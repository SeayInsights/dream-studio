"""Tests for YAML config.yml reading in model_selector — _read_config_yml_tier and fallback."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.model_selector import (  # noqa: E402
    _read_config_yml_tier,
    _read_model_tier,
    get_model_for_skill,
)


# ---------------------------------------------------------------------------
# Unit tests for _read_config_yml_tier
# ---------------------------------------------------------------------------

class TestReadConfigYmlTier:

    def test_valid_config_yml_opus(self, tmp_path: Path) -> None:
        """config.yml with model_tier: opus returns 'opus'."""
        cfg = tmp_path / "config.yml"
        cfg.write_text("name: think\nmodel_tier: opus\ndescription: Test skill\n")
        assert _read_config_yml_tier(cfg) == "opus"

    def test_valid_config_yml_sonnet(self, tmp_path: Path) -> None:
        """config.yml with model_tier: sonnet returns 'sonnet'."""
        cfg = tmp_path / "config.yml"
        cfg.write_text("name: build\nmodel_tier: sonnet\ndescription: Build skill\n")
        assert _read_config_yml_tier(cfg) == "sonnet"

    def test_valid_config_yml_haiku(self, tmp_path: Path) -> None:
        """config.yml with model_tier: haiku returns 'haiku'."""
        cfg = tmp_path / "config.yml"
        cfg.write_text("name: explain\nmodel_tier: haiku\ndescription: Explain skill\n")
        assert _read_config_yml_tier(cfg) == "haiku"

    def test_config_yml_without_model_tier(self, tmp_path: Path) -> None:
        """config.yml with no model_tier key returns None."""
        cfg = tmp_path / "config.yml"
        cfg.write_text("name: test\ndescription: No tier declared\npack: core\n")
        assert _read_config_yml_tier(cfg) is None

    def test_missing_config_yml(self, tmp_path: Path) -> None:
        """Non-existent config.yml returns None."""
        assert _read_config_yml_tier(tmp_path / "config.yml") is None

    def test_malformed_yaml(self, tmp_path: Path) -> None:
        """Malformed YAML returns None without raising."""
        cfg = tmp_path / "config.yml"
        cfg.write_text("name: [unclosed bracket\nmodel_tier: opus\n")
        assert _read_config_yml_tier(cfg) is None

    def test_invalid_tier_value(self, tmp_path: Path) -> None:
        """model_tier set to an unrecognised value returns None."""
        cfg = tmp_path / "config.yml"
        cfg.write_text("name: test\nmodel_tier: gpt-4-turbo\ndescription: Bad tier\n")
        assert _read_config_yml_tier(cfg) is None

    def test_model_tier_with_extra_whitespace(self, tmp_path: Path) -> None:
        """model_tier value with surrounding whitespace is normalised."""
        cfg = tmp_path / "config.yml"
        # YAML scalar with quoted whitespace padding
        cfg.write_text("name: test\nmodel_tier: '  opus  '\ndescription: Padded\n")
        assert _read_config_yml_tier(cfg) == "opus"

    def test_model_tier_uppercase_normalised(self, tmp_path: Path) -> None:
        """model_tier in uppercase is case-folded to lowercase."""
        cfg = tmp_path / "config.yml"
        cfg.write_text("name: test\nmodel_tier: SONNET\ndescription: Upper\n")
        assert _read_config_yml_tier(cfg) == "sonnet"

    def test_yaml_is_not_a_dict(self, tmp_path: Path) -> None:
        """config.yml that parses to a non-dict (e.g. list) returns None."""
        cfg = tmp_path / "config.yml"
        cfg.write_text("- item1\n- item2\n")
        assert _read_config_yml_tier(cfg) is None


# ---------------------------------------------------------------------------
# Integration: _read_model_tier with config.yml present vs absent
# ---------------------------------------------------------------------------

class TestReadModelTierWithConfigYml:

    def test_prefers_config_yml_over_frontmatter(self, tmp_path: Path) -> None:
        """When config.yml exists, its tier takes precedence over SKILL.md frontmatter."""
        skill_dir = tmp_path / "myskill"
        skill_dir.mkdir()

        # SKILL.md has frontmatter saying haiku
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(textwrap.dedent("""\
            ---
            name: myskill
            model_tier: haiku
            description: Test
            ---
            # Body
        """))

        # config.yml says opus — should win
        cfg = skill_dir / "config.yml"
        cfg.write_text("name: myskill\nmodel_tier: opus\ndescription: Test\n")

        assert _read_model_tier(skill_md) == "opus"

    def test_falls_back_to_frontmatter_when_no_config_yml(self, tmp_path: Path) -> None:
        """When config.yml is absent, SKILL.md frontmatter is used as fallback."""
        skill_dir = tmp_path / "myskill"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(textwrap.dedent("""\
            ---
            name: myskill
            model_tier: sonnet
            description: Test
            ---
            # Body
        """))

        # No config.yml written — fallback must kick in
        assert _read_model_tier(skill_md) == "sonnet"

    def test_config_yml_missing_tier_falls_back_to_frontmatter(self, tmp_path: Path) -> None:
        """config.yml exists but has no model_tier → falls back to SKILL.md frontmatter."""
        skill_dir = tmp_path / "myskill"
        skill_dir.mkdir()

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(textwrap.dedent("""\
            ---
            name: myskill
            model_tier: haiku
            description: Test
            ---
            # Body
        """))

        cfg = skill_dir / "config.yml"
        cfg.write_text("name: myskill\ndescription: No tier here\n")

        assert _read_model_tier(skill_md) == "haiku"


# ---------------------------------------------------------------------------
# End-to-end: get_model_for_skill reads real config.yml files
# ---------------------------------------------------------------------------

class TestGetModelForSkillFromConfigYml:
    """Integration tests against the real config.yml files in the repo."""

    def test_think_reads_opus_from_config_yml(self) -> None:
        """core think → config.yml should declare opus."""
        assert get_model_for_skill("dream-studio:core think") == "opus"

    def test_build_reads_sonnet_from_config_yml(self) -> None:
        """core build → config.yml should declare sonnet."""
        assert get_model_for_skill("dream-studio:core build") == "sonnet"

    def test_explain_reads_haiku_from_config_yml(self) -> None:
        """core explain → config.yml should declare haiku."""
        assert get_model_for_skill("dream-studio:core explain") == "haiku"

    def test_secure_reads_opus_from_config_yml(self) -> None:
        """quality secure → config.yml should declare opus."""
        assert get_model_for_skill("dream-studio:quality secure") == "opus"

    def test_binary_scan_reads_opus_from_config_yml(self) -> None:
        """security binary-scan → config.yml should declare opus."""
        assert get_model_for_skill("dream-studio:security binary-scan") == "opus"

    def test_jit_reads_haiku_from_config_yml(self) -> None:
        """setup jit → config.yml should declare haiku."""
        assert get_model_for_skill("dream-studio:setup jit") == "haiku"
