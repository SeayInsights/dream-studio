"""Tests for on-skill-complete config.yml reading."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packs" / "meta" / "hooks"))

from importlib import util as _ilu

_spec = _ilu.spec_from_file_location(
    "on_skill_complete",
    Path(__file__).resolve().parents[2] / "packs" / "meta" / "hooks" / "on-skill-complete.py",
)
_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_read_chain_suggests = _mod._read_chain_suggests


class TestReadChainSuggests:

    def test_reads_chain_suggests_from_config_yml(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yml"
        cfg.write_text(
            "name: think\n"
            "model_tier: opus\n"
            "chain_suggests:\n"
            '- condition: "always"\n'
            '  next: "plan"\n'
            '  prompt: "Spec approved?"\n',
            encoding="utf-8",
        )
        result = _read_chain_suggests(cfg)
        assert len(result) == 1
        assert result[0]["condition"] == "always"
        assert result[0]["next"] == "plan"
        assert result[0]["prompt"] == "Spec approved?"

    def test_missing_config_yml_returns_empty(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yml"
        assert _read_chain_suggests(cfg) == []

    def test_no_chain_suggests_key_returns_empty(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yml"
        cfg.write_text("name: build\nmodel_tier: sonnet\n", encoding="utf-8")
        assert _read_chain_suggests(cfg) == []

    def test_malformed_yaml_returns_empty(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yml"
        cfg.write_text(":::bad yaml{{{\n", encoding="utf-8")
        assert _read_chain_suggests(cfg) == []

    def test_multiple_chain_suggests(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yml"
        cfg.write_text(
            "name: debug\n"
            "chain_suggests:\n"
            '- condition: "root_cause_found"\n'
            '  next: "plan"\n'
            '  prompt: "Plan the fix?"\n'
            '- condition: "debug_iterations_gte_3"\n'
            '  next: "learn"\n'
            '  prompt: "Capture lesson?"\n',
            encoding="utf-8",
        )
        result = _read_chain_suggests(cfg)
        assert len(result) == 2
        assert result[0]["next"] == "plan"
        assert result[1]["next"] == "learn"

    def test_reads_real_config_yml(self) -> None:
        """Smoke test against an actual config.yml in the repo."""
        repo_root = Path(__file__).resolve().parents[2]
        think_config = repo_root / "skills" / "core" / "modes" / "think" / "config.yml"
        if think_config.exists():
            result = _read_chain_suggests(think_config)
            assert len(result) >= 1
            assert any(e.get("next") == "plan" for e in result)
