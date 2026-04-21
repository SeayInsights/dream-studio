"""Tests for on-game-validate hook."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conftest import load_handler  # noqa: E402

mod = load_handler("on-game-validate")


@pytest.fixture
def godot_project(tmp_path: Path) -> Path:
    """Create a minimal Godot project structure."""
    (tmp_path / "project.godot").write_text(
        '[application]\nconfig/features=PackedStringArray("4.3")\n', encoding="utf-8"
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scenes").mkdir()
    (tmp_path / "assets").mkdir()
    return tmp_path


@pytest.fixture
def gameplay_dir(godot_project: Path) -> Path:
    d = godot_project / "scripts" / "gameplay"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def ai_dir(godot_project: Path) -> Path:
    d = godot_project / "scripts" / "ai"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def ui_dir(godot_project: Path) -> Path:
    d = godot_project / "scripts" / "ui"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def data_dir(godot_project: Path) -> Path:
    d = godot_project / "data"
    d.mkdir(parents=True)
    return d


class TestDetectProject:
    def test_finds_godot_project(self, godot_project: Path):
        test_file = godot_project / "scripts" / "test.gd"
        test_file.write_text("extends Node", encoding="utf-8")
        ctx = mod.detect_project(test_file)
        assert ctx is not None
        assert ctx.root == godot_project
        assert ctx.godot_version == "4.3"
        assert ctx.has_standard_structure is True

    def test_returns_none_outside_project(self, tmp_path: Path):
        test_file = tmp_path / "random.gd"
        test_file.write_text("extends Node", encoding="utf-8")
        assert mod.detect_project(test_file) is None

    def test_skips_plugin_cache(self, tmp_path: Path):
        cache = tmp_path / ".claude" / "plugins" / "cache" / "test"
        cache.mkdir(parents=True)
        (cache / "project.godot").write_text("[application]", encoding="utf-8")
        (cache / "scripts").mkdir()
        test_file = cache / "test.gd"
        test_file.write_text("extends Node", encoding="utf-8")
        assert mod.detect_project(test_file) is None

    def test_requires_directory_markers(self, tmp_path: Path):
        (tmp_path / "project.godot").write_text("[application]", encoding="utf-8")
        test_file = tmp_path / "test.gd"
        test_file.write_text("extends Node", encoding="utf-8")
        assert mod.detect_project(test_file) is None

    def test_requires_two_markers(self, tmp_path: Path):
        """One marker is not enough — need 2+ to confirm it's a real project."""
        (tmp_path / "project.godot").write_text("[application]", encoding="utf-8")
        (tmp_path / "scripts").mkdir()
        test_file = tmp_path / "scripts" / "test.gd"
        test_file.write_text("extends Node", encoding="utf-8")
        assert mod.detect_project(test_file) is None

    def test_two_markers_sufficient(self, tmp_path: Path):
        (tmp_path / "project.godot").write_text(
            '[application]\nconfig/features=PackedStringArray("4.3")\n', encoding="utf-8"
        )
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scenes").mkdir()
        test_file = tmp_path / "scripts" / "test.gd"
        test_file.write_text("extends Node", encoding="utf-8")
        ctx = mod.detect_project(test_file)
        assert ctx is not None

    def test_parses_version_from_features(self, godot_project: Path):
        test_file = godot_project / "scripts" / "test.gd"
        test_file.write_text("extends Node", encoding="utf-8")
        ctx = mod.detect_project(test_file)
        assert ctx is not None
        assert ctx.godot_version == "4.3"

    def test_parses_config_version_5(self, tmp_path: Path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scenes").mkdir()
        (tmp_path / "project.godot").write_text("config_version=5\n", encoding="utf-8")
        test_file = tmp_path / "scripts" / "test.gd"
        test_file.write_text("extends Node", encoding="utf-8")
        ctx = mod.detect_project(test_file)
        assert ctx is not None
        assert ctx.godot_version == "4.x"


class TestClassifyPath:
    def test_gameplay_keywords(self):
        assert "gameplay" in mod.classify_path("scripts/gameplay/player.gd")
        assert "gameplay" in mod.classify_path("scripts/combat/sword.gd")
        assert "gameplay" in mod.classify_path("scripts/mechanics/jump.gd")

    def test_ai_keywords(self):
        assert "ai" in mod.classify_path("scripts/ai/enemy.gd")
        assert "ai" in mod.classify_path("scripts/npc/villager.gd")
        assert "ai" in mod.classify_path("scripts/enemies/boss.gd")

    def test_ui_keywords(self):
        assert "ui" in mod.classify_path("scripts/ui/health_bar.gd")
        assert "ui" in mod.classify_path("scenes/hud/minimap.gd")
        assert "ui" in mod.classify_path("scripts/menu/main_menu.gd")

    def test_networking_keywords(self):
        assert "networking" in mod.classify_path("scripts/multiplayer/lobby.gd")
        assert "networking" in mod.classify_path("scripts/net/rpc_handler.gd")

    def test_no_match(self):
        assert mod.classify_path("scripts/utils/helpers.gd") == set()

    def test_filename_keyword_match(self, tmp_path: Path):
        f = tmp_path / "combat_system.gd"
        f.write_text("extends Node", encoding="utf-8")
        assert "gameplay" in mod.classify_path("scripts/combat_system.gd", f)

    def test_content_fallback(self, tmp_path: Path):
        f = tmp_path / "thing.gd"
        f.write_text("extends CharacterBody2D\nvar velocity = Vector2.ZERO", encoding="utf-8")
        assert "gameplay" in mod.classify_path("scripts/thing.gd", f)

    def test_content_fallback_ui(self, tmp_path: Path):
        f = tmp_path / "widget.gd"
        f.write_text("extends Control\n@onready var label = $Label", encoding="utf-8")
        assert "ui" in mod.classify_path("scripts/widget.gd", f)

    def test_content_fallback_networking(self, tmp_path: Path):
        f = tmp_path / "sync.gd"
        f.write_text("extends Node\n@rpc\nfunc send_input(data):\n    pass", encoding="utf-8")
        assert "networking" in mod.classify_path("scripts/sync.gd", f)


class TestValidateGdscript:
    def test_detects_hardcoded_const(self, gameplay_dir: Path):
        f = gameplay_dir / "player.gd"
        f.write_text("extends Node\nconst SPEED = 200.0\n", encoding="utf-8")
        result = mod.validate_gdscript(f, {"gameplay"})
        assert any("magic number" in w for w in result.warnings)

    def test_ignores_exports(self, gameplay_dir: Path):
        f = gameplay_dir / "player.gd"
        f.write_text("extends Node\n@export var speed: float = 200.0\n", encoding="utf-8")
        result = mod.validate_gdscript(f, {"gameplay"})
        assert not result.warnings

    def test_ignores_comments(self, gameplay_dir: Path):
        f = gameplay_dir / "player.gd"
        f.write_text("extends Node\n# const SPEED = 200.0\n", encoding="utf-8")
        result = mod.validate_gdscript(f, {"gameplay"})
        assert not result.warnings

    def test_detects_ui_reference(self, gameplay_dir: Path):
        f = gameplay_dir / "player.gd"
        f.write_text('extends Node\nvar label = $UI/Label\n', encoding="utf-8")
        result = mod.validate_gdscript(f, {"gameplay"})
        assert any("UI" in w for w in result.warnings)

    def test_no_warnings_outside_gameplay(self, tmp_path: Path):
        f = tmp_path / "util.gd"
        f.write_text("extends Node\nconst MAX_RETRIES = 3\n", encoding="utf-8")
        result = mod.validate_gdscript(f, set())
        assert not result.warnings

    def test_detects_ui_state_mutation(self, ui_dir: Path):
        f = ui_dir / "hud.gd"
        f.write_text("extends Control\nfunc update():\n    GameState.health += 10\n", encoding="utf-8")
        result = mod.validate_gdscript(f, {"ui"})
        assert any("mutating game state" in w for w in result.warnings)


class TestSuppressionPragma:
    def test_ignore_file_suppresses_all(self, gameplay_dir: Path):
        f = gameplay_dir / "player.gd"
        f.write_text("# ds:ignore-file\nextends Node\nconst SPEED = 200.0\n", encoding="utf-8")
        result = mod.validate_gdscript(f, {"gameplay"})
        assert not result.warnings

    def test_inline_ignore_suppresses_line(self, gameplay_dir: Path):
        f = gameplay_dir / "player.gd"
        f.write_text("extends Node\nconst SPEED = 200.0  # ds:ignore\n", encoding="utf-8")
        result = mod.validate_gdscript(f, {"gameplay"})
        assert not result.warnings

    def test_ignore_next_line_suppresses(self, gameplay_dir: Path):
        f = gameplay_dir / "player.gd"
        f.write_text("extends Node\n# ds:ignore-next-line\nconst SPEED = 200.0\n", encoding="utf-8")
        result = mod.validate_gdscript(f, {"gameplay"})
        assert not result.warnings

    def test_ignore_next_line_only_affects_next(self, gameplay_dir: Path):
        f = gameplay_dir / "player.gd"
        f.write_text(
            "extends Node\n# ds:ignore-next-line\nconst SPEED = 200.0\nconst HEALTH = 100\n",
            encoding="utf-8",
        )
        result = mod.validate_gdscript(f, {"gameplay"})
        assert len(result.warnings) == 1
        assert "HEALTH" not in result.warnings[0] or "magic number" in result.warnings[0]

    def test_no_pragma_still_warns(self, gameplay_dir: Path):
        f = gameplay_dir / "player.gd"
        f.write_text("extends Node\nconst SPEED = 200.0\nconst HEALTH = 100\n", encoding="utf-8")
        result = mod.validate_gdscript(f, {"gameplay"})
        assert len(result.warnings) == 2

    def test_suppress_ui_reference(self, gameplay_dir: Path):
        f = gameplay_dir / "player.gd"
        f.write_text('extends Node\nvar label = $UI/Label  # ds:ignore\n', encoding="utf-8")
        result = mod.validate_gdscript(f, {"gameplay"})
        assert not any("UI" in w for w in result.warnings)

    def test_file_pragma_must_be_in_first_5_lines(self, gameplay_dir: Path):
        f = gameplay_dir / "player.gd"
        f.write_text(
            "extends Node\nvar a = 1\nvar b = 2\nvar c = 3\nvar d = 4\nvar e = 5\n# ds:ignore-file\nconst SPEED = 200.0\n",
            encoding="utf-8",
        )
        result = mod.validate_gdscript(f, {"gameplay"})
        assert any("magic number" in w for w in result.warnings)


class TestValidateJsonData:
    def test_valid_json(self, data_dir: Path):
        f = data_dir / "items.json"
        f.write_text('{"items": [{"name": "sword"}]}', encoding="utf-8")
        result = mod.validate_json_data(f, "data/items.json")
        assert not result.errors

    def test_invalid_json(self, data_dir: Path):
        f = data_dir / "bad.json"
        f.write_text('{"broken": }', encoding="utf-8")
        result = mod.validate_json_data(f, "data/bad.json")
        assert any("INVALID JSON" in e for e in result.errors)

    def test_empty_json(self, data_dir: Path):
        f = data_dir / "empty.json"
        f.write_text("", encoding="utf-8")
        result = mod.validate_json_data(f, "data/empty.json")
        assert any("empty" in e.lower() for e in result.errors)

    def test_extreme_values_in_balance(self, data_dir: Path):
        f = data_dir / "balance.json"
        f.write_text('{"units": [{"speed": 99999999}]}', encoding="utf-8")
        result = mod.validate_json_data(f, "data/balance.json")
        assert any("extreme" in w for w in result.warnings)

    def test_schema_consistency(self, data_dir: Path):
        f = data_dir / "units.json"
        f.write_text('{"units": [{"name": "a", "hp": 10}, {"name": "b"}]}', encoding="utf-8")
        result = mod.validate_json_data(f, "data/units.json")
        assert any("missing keys" in w for w in result.warnings)


class TestValidateAssetNaming:
    def test_valid_prefix(self, tmp_path: Path):
        f = tmp_path / "assets" / "chr_hero.glb"
        f.parent.mkdir(parents=True)
        f.write_text("", encoding="utf-8")
        result = mod.validate_asset_naming(f, "assets/chr_hero.glb")
        assert not result.warnings

    def test_missing_prefix(self, tmp_path: Path):
        f = tmp_path / "assets" / "hero.glb"
        f.parent.mkdir(parents=True)
        f.write_text("", encoding="utf-8")
        result = mod.validate_asset_naming(f, "assets/hero.glb")
        assert any("prefix" in w for w in result.warnings)

    def test_spaces_in_name(self, tmp_path: Path):
        f = tmp_path / "assets" / "my hero.glb"
        f.parent.mkdir(parents=True)
        f.write_text("", encoding="utf-8")
        result = mod.validate_asset_naming(f, "assets/my hero.glb")
        assert any("spaces" in e for e in result.errors)

    def test_ignores_non_asset_dirs(self, tmp_path: Path):
        f = tmp_path / "scripts" / "hero.glb"
        f.parent.mkdir(parents=True)
        f.write_text("", encoding="utf-8")
        result = mod.validate_asset_naming(f, "scripts/hero.glb")
        assert not result.warnings and not result.errors


class TestVersionStaleness:
    def test_current_version_no_warning(self, godot_project: Path):
        ctx = mod.ProjectContext(root=godot_project, godot_version="4.3", has_standard_structure=True)
        assert mod.check_version_staleness(ctx) == []

    def test_newer_version_warns(self, godot_project: Path):
        ctx = mod.ProjectContext(root=godot_project, godot_version="4.5", has_standard_structure=True)
        warnings = mod.check_version_staleness(ctx)
        assert len(warnings) == 1
        assert "outdated" in warnings[0]

    def test_unknown_version_no_warning(self, godot_project: Path):
        ctx = mod.ProjectContext(root=godot_project, godot_version="unknown", has_standard_structure=True)
        assert mod.check_version_staleness(ctx) == []
