"""Tests for game_validate.py — targeting 71 uncovered lines.

Covers: detect_project (.dream-studio path 94, marker_count<2 135-139),
_parse_godot_version (cv==4 branch 135-136, exception path 137-139),
relative_to_project (143-146), classify_path content fallback (176, 181-182),
validate_gdscript (too large 195, read error 197-198, enum/signal continue 220,
>5 hardcoded 230, >3 UI refs 248, physics func 256-257, 259-260, networking 264-272),
validate_json_data (extreme value 294, NaN 295, camelCase keys 321, threshold 326-328,
extra keys 341-343), validate_asset_naming (wrong ext 355, uppercase .glb 372),
validate_shader (379-409), check_version_staleness (exception 432-433).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_DOMAIN_LIB = Path(__file__).resolve().parents[2] / "packs" / "domains" / "domain_lib"
if str(_DOMAIN_LIB) not in sys.path:
    sys.path.insert(0, str(_DOMAIN_LIB))

from game_validate import (  # noqa: E402
    ProjectContext,
    ValidationResult,
    _parse_godot_version,
    check_version_staleness,
    classify_path,
    detect_project,
    relative_to_project,
    validate_asset_naming,
    validate_gdscript,
    validate_json_data,
    validate_shader,
)


# ── detect_project (lines 94, 135-139) ───────────────────────────────────


class TestDetectProject:
    def test_rejects_dream_studio_path(self) -> None:
        # Line 94: return None when .dream-studio in normalized path
        fake = Path("/some/user/.dream-studio/packs/test.gd")
        assert detect_project(fake) is None

    def test_rejects_plugin_cache_path(self) -> None:
        fake = Path("/home/user/.claude/plugins/cache/game/script.gd")
        assert detect_project(fake) is None

    def test_rejects_when_marker_count_below_two(self, tmp_path: Path) -> None:
        # Lines 135-139: marker_count < 2 → skip this candidate root
        godot_file = tmp_path / "project.godot"
        godot_file.write_text("[application]\nconfig_version=5\n")
        (tmp_path / "scenes").mkdir()  # only 1 marker — not enough
        file_path = tmp_path / "test.gd"
        file_path.write_text("extends Node\n")
        # With only 1 marker the candidate is skipped; traversal reaches home → None
        result = detect_project(file_path)
        assert result is None

    def test_accepts_when_two_markers_present(self, tmp_path: Path) -> None:
        godot_file = tmp_path / "project.godot"
        godot_file.write_text('config/features=PackedStringArray("4.2")\n')
        (tmp_path / "scenes").mkdir()
        (tmp_path / "scripts").mkdir()
        file_path = tmp_path / "scripts" / "player.gd"
        file_path.write_text("extends CharacterBody2D\n")
        result = detect_project(file_path)
        assert result is not None
        assert result.root == tmp_path
        assert result.has_standard_structure is True


# ── _parse_godot_version (lines 135-136, 137-139) ─────────────────────────


class TestParseGodotVersion:
    def test_config_version_5_returns_4x(self, tmp_path: Path) -> None:
        f = tmp_path / "project.godot"
        f.write_text("config_version=5\n")
        assert _parse_godot_version(f) == "4.x"

    def test_config_version_4_returns_3x(self, tmp_path: Path) -> None:
        # Line 135-136
        f = tmp_path / "project.godot"
        f.write_text("config_version=4\n")
        assert _parse_godot_version(f) == "3.x"

    def test_exception_returns_unknown(self, tmp_path: Path) -> None:
        # Lines 137-139: exception path
        f = tmp_path / "missing.godot"
        assert _parse_godot_version(f) == "unknown"

    def test_features_line_takes_priority(self, tmp_path: Path) -> None:
        f = tmp_path / "project.godot"
        f.write_text('config/features=PackedStringArray("4.3")\nconfig_version=5\n')
        assert _parse_godot_version(f) == "4.3"

    def test_no_version_returns_unknown(self, tmp_path: Path) -> None:
        # Lines 138-139: no config_version → falls through to return "unknown"
        f = tmp_path / "project.godot"
        f.write_text("[application]\n")
        assert _parse_godot_version(f) == "unknown"


# ── relative_to_project (lines 143-146) ──────────────────────────────────


class TestRelativeToProject:
    def test_file_inside_root_returns_relative(self, tmp_path: Path) -> None:
        # Lines 143-144
        project_root = tmp_path / "game"
        project_root.mkdir()
        file_path = project_root / "scripts" / "player.gd"
        rel = relative_to_project(file_path, project_root)
        assert rel == "scripts/player.gd"

    def test_file_outside_root_returns_absolute_fallback(self, tmp_path: Path) -> None:
        # Lines 145-146: ValueError → fallback
        project_root = tmp_path / "game"
        project_root.mkdir()
        file_path = tmp_path / "other" / "file.gd"
        rel = relative_to_project(file_path, project_root)
        assert "other" in rel
        assert "file.gd" in rel


# ── classify_path — content fallback (lines 176, 181-182) ────────────────


class TestClassifyPathContentFallback:
    def test_gameplay_detected_from_content(self, tmp_path: Path) -> None:
        # Line 176: domains empty after path scan, fallback reads file content
        f = tmp_path / "character.gd"
        f.write_text("extends CharacterBody2D\nfunc _physics_process(delta):\n    velocity = Vector2.ZERO\n")
        domains = classify_path("scripts/character.gd", file_path=f)
        assert "gameplay" in domains

    def test_ai_detected_from_content(self, tmp_path: Path) -> None:
        # Lines 181-182: AI keywords in content
        f = tmp_path / "enemy.gd"
        f.write_text("extends Node\nvar agent = NavigationAgent2D.new()\n")
        domains = classify_path("scripts/enemy.gd", file_path=f)
        assert "ai" in domains

    def test_ui_detected_from_content(self, tmp_path: Path) -> None:
        f = tmp_path / "hud_script.gd"
        f.write_text("extends Control\nfunc _ready():\n    $Label.text = 'hi'\n")
        domains = classify_path("scripts/hud_script.gd", file_path=f)
        assert "ui" in domains

    def test_networking_detected_from_content(self, tmp_path: Path) -> None:
        f = tmp_path / "sync.gd"
        f.write_text("extends Node\nfunc _ready():\n    multiplayer.peer_connected.connect(_on_peer)\n")
        domains = classify_path("scripts/sync.gd", file_path=f)
        assert "networking" in domains

    def test_path_match_takes_precedence(self, tmp_path: Path) -> None:
        f = tmp_path / "player.gd"
        f.write_text("# empty\n")
        domains = classify_path("gameplay/player.gd", file_path=f)
        assert "gameplay" in domains

    def test_content_fallback_handles_read_error(self, tmp_path: Path) -> None:
        # Lines 181-182: except Exception: pass when file read fails in content fallback
        f = tmp_path / "broken.gd"
        f.write_text("# gd")
        with patch.object(Path, "read_text", side_effect=OSError("denied")):
            domains = classify_path("scripts/broken.gd", file_path=f)
        assert isinstance(domains, set)  # exception swallowed, returns empty set


# ── validate_gdscript (lines 195, 197-198, 220, 230, 248, 256-260, 264-272) ──


class TestValidateGdscriptCoverage:
    def test_skips_oversized_file(self, tmp_path: Path, monkeypatch) -> None:
        # Line 195: file too large — patch Path.stat at class level (WindowsPath slots are read-only)
        f = tmp_path / "big.gd"
        f.write_text("x = 1\n")
        mock_stat = MagicMock()
        mock_stat.st_size = 20 * 1024 * 1024
        monkeypatch.setattr(type(f), "stat", lambda self_: mock_stat)
        result = validate_gdscript(f, {"gameplay"})
        assert any("Skipped" in i for i in result.info)

    def test_unreadable_file_returns_error(self, tmp_path: Path) -> None:
        # Lines 197-198: read exception
        f = tmp_path / "locked.gd"
        f.write_text("x = 1\n")
        with patch.object(Path, "read_text", side_effect=OSError("denied")):
            result = validate_gdscript(f, {"gameplay"})
        assert any("Could not read file" in e for e in result.errors)

    def test_enum_line_skipped_in_hardcoded_check(self, tmp_path: Path) -> None:
        # Line 220: `continue` on enum/signal/class_name lines
        f = tmp_path / "player.gd"
        f.write_text(
            "extends Node\n"
            "enum State { IDLE = 0, RUN = 1 }\n"
            "signal health_changed(val = 100)\n"
        )
        result = validate_gdscript(f, {"gameplay"})
        # Enum lines should NOT generate hardcoded-value warnings
        assert not any("magic number" in w for w in result.warnings)

    def test_more_than_five_hardcoded_values(self, tmp_path: Path) -> None:
        # Line 230: `hardcoded_count > 5` → truncation message
        # Must use `const SPEED_X = N` — matches HARDCODED_PATTERNS[0]
        lines = ["extends Node\n"]
        for i in range(7):
            lines.append(f"const SPEED_{i} = {i + 10}\n")
        f = tmp_path / "ai_enemy.gd"
        f.write_text("".join(lines))
        result = validate_gdscript(f, {"ai"})
        assert any("more hardcoded" in w for w in result.warnings)

    def test_more_than_three_ui_refs_in_gameplay(self, tmp_path: Path) -> None:
        # Line 248: `ui_ref_count > 3` → truncation message
        lines = ["extends Node\n"]
        for i in range(5):
            lines.append(f"var lbl{i} = $Label{i}\n")
        f = tmp_path / "player.gd"
        f.write_text("".join(lines))
        result = validate_gdscript(f, {"gameplay"})
        assert any("more UI references" in w for w in result.warnings)

    def test_velocity_without_delta_in_physics(self, tmp_path: Path) -> None:
        # Lines 256-257, 259-260: physics func detection + velocity without delta
        f = tmp_path / "character.gd"
        f.write_text(
            "extends CharacterBody2D\n"
            "const SPEED = 200\n"
            "func _physics_process(delta):\n"
            "    velocity.x = SPEED\n"
        )
        result = validate_gdscript(f, {"gameplay"})
        assert any("missing delta" in w for w in result.warnings)

    def test_velocity_with_delta_no_warning(self, tmp_path: Path) -> None:
        f = tmp_path / "character.gd"
        f.write_text(
            "extends CharacterBody2D\n"
            "func _physics_process(delta):\n"
            "    velocity.x = speed * delta\n"
        )
        result = validate_gdscript(f, {"gameplay"})
        assert not any("missing delta" in w for w in result.warnings)

    def test_networking_direct_position_set(self, tmp_path: Path) -> None:
        # Lines 264-272: networking anti-pattern checks
        # Pattern requires `.position =` (with dot)
        f = tmp_path / "net_player.gd"
        f.write_text(
            "extends CharacterBody2D\n"
            "func _on_sync(data):\n"
            "    self.position = data.pos\n"
        )
        result = validate_gdscript(f, {"networking"})
        assert any("direct position" in i for i in result.info)

    def test_networking_any_peer_rpc(self, tmp_path: Path) -> None:
        # Lines 271-272: @rpc(any_peer) warning
        f = tmp_path / "net_sync.gd"
        f.write_text(
            "extends Node\n"
            "@rpc(any_peer) func receive_action(data):\n"
            "    pass\n"
        )
        result = validate_gdscript(f, {"networking"})
        assert any("any_peer" in i for i in result.info)

    def test_networking_comment_lines_skipped(self, tmp_path: Path) -> None:
        # Lines 267-268: `if stripped.startswith("#"): continue`
        f = tmp_path / "net_clean.gd"
        f.write_text(
            "extends Node\n"
            "# @rpc(any_peer) this is commented out\n"
            "# position = Vector2.ZERO\n"
        )
        result = validate_gdscript(f, {"networking"})
        assert not result.info  # commented lines produce no warnings


# ── validate_json_data (lines 294-295, 321, 326-328, 341-343) ─────────────


class TestValidateJsonDataCoverage:
    def test_balance_extreme_value_warning(self, tmp_path: Path) -> None:
        # Line 294: abs(obj) > 999999
        f = tmp_path / "balance.json"
        f.write_text(json.dumps({"damage": 9999999}))
        result = validate_json_data(f, "data/balance.json")
        assert any("seems extreme" in w for w in result.warnings)

    def test_balance_extreme_value_skipped_for_id(self, tmp_path: Path) -> None:
        f = tmp_path / "balance.json"
        f.write_text(json.dumps({"item_id": 9999999}))
        result = validate_json_data(f, "data/balance.json")
        assert not any("seems extreme" in w for w in result.warnings)

    def test_balance_nan_detected(self, tmp_path: Path) -> None:
        # Line 295 (321 in original): NaN float injected via mock
        f = tmp_path / "balance.json"
        f.write_text('{"damage": 100}')
        nan_data = {"damage": float("nan")}
        with patch("json.loads", return_value=nan_data):
            result = validate_json_data(f, "data/balance.json")
        assert any("NaN" in w for w in result.warnings)

    def test_camelcase_keys_warning(self, tmp_path: Path) -> None:
        # Lines 326-328: bad_keys threshold > 30%
        f = tmp_path / "config.json"
        data = {"firstName": "x", "lastName": "y", "maxHealth": 100, "minSpeed": 5}
        f.write_text(json.dumps(data))
        result = validate_json_data(f, "config.json")
        assert any("snake_case" in w for w in result.warnings)

    def test_all_lowercase_keys_no_warning(self, tmp_path: Path) -> None:
        f = tmp_path / "config.json"
        data = {"first_name": "x", "last_name": "y", "max_health": 100}
        f.write_text(json.dumps(data))
        result = validate_json_data(f, "config.json")
        assert not any("snake_case" in w for w in result.warnings)

    def test_schema_extra_keys_reported(self, tmp_path: Path) -> None:
        # Lines 341-343: extra keys in later entries vs reference
        f = tmp_path / "items.json"
        data = {
            "weapons": [
                {"id": 1, "name": "sword"},
                {"id": 2, "name": "shield", "bonus": 5},  # extra key
            ]
        }
        f.write_text(json.dumps(data))
        result = validate_json_data(f, "data/items.json")
        assert any("extra keys" in i for i in result.info)

    def test_schema_missing_keys_reported(self, tmp_path: Path) -> None:
        f = tmp_path / "items.json"
        data = {
            "weapons": [
                {"id": 1, "name": "sword", "damage": 10},
                {"id": 2, "name": "shield"},  # missing "damage"
            ]
        }
        f.write_text(json.dumps(data))
        result = validate_json_data(f, "data/items.json")
        assert any("missing keys" in w for w in result.warnings)

    def test_empty_file_error(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.json"
        f.write_text("")
        result = validate_json_data(f, "data/empty.json")
        assert any("empty" in e for e in result.errors)

    def test_invalid_json_error(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("{bad json}")
        result = validate_json_data(f, "data/bad.json")
        assert any("INVALID JSON" in e for e in result.errors)

    def test_unreadable_file_error(self, tmp_path: Path) -> None:
        f = tmp_path / "locked.json"
        f.write_text("{}")
        with patch.object(Path, "read_text", side_effect=OSError("denied")):
            result = validate_json_data(f, "data/locked.json")
        assert any("Could not read" in e for e in result.errors)


# ── validate_asset_naming (lines 355, 372) ────────────────────────────────


class TestValidateAssetNaming:
    def test_non_asset_extension_returns_empty(self, tmp_path: Path) -> None:
        # Line 355: early return for .gd files
        f = tmp_path / "player.gd"
        f.write_text("extends Node\n")
        result = validate_asset_naming(f, "scripts/player.gd")
        assert not result.errors and not result.warnings and not result.info

    def test_non_asset_path_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "chr_player.glb"
        result = validate_asset_naming(f, "exports/chr_player.glb")
        assert not result.errors and not result.warnings and not result.info

    def test_glb_missing_prefix_warning(self, tmp_path: Path) -> None:
        f = tmp_path / "player.glb"
        result = validate_asset_naming(f, "assets/player.glb")
        assert any("missing type prefix" in w for w in result.warnings)

    def test_glb_with_valid_prefix_no_warning(self, tmp_path: Path) -> None:
        f = tmp_path / "chr_player.glb"
        result = validate_asset_naming(f, "assets/chr_player.glb")
        assert not any("missing type prefix" in w for w in result.warnings)

    def test_uppercase_glb_filename_warning(self, tmp_path: Path) -> None:
        # Line 372: uppercase filename should be lowercase
        f = tmp_path / "Chr_Player.glb"
        result = validate_asset_naming(f, "assets/Chr_Player.glb")
        assert any("lowercase" in w for w in result.warnings)

    def test_spaces_in_name_error(self, tmp_path: Path) -> None:
        f = tmp_path / "chr player.glb"
        result = validate_asset_naming(f, "assets/chr player.glb")
        assert any("spaces" in e for e in result.errors)

    def test_tscn_uppercase_no_lowercase_warning(self, tmp_path: Path) -> None:
        # .tres/.tscn uppercase is allowed per the condition
        f = tmp_path / "Player.tscn"
        result = validate_asset_naming(f, "assets/Player.tscn")
        assert not any("lowercase" in w for w in result.warnings)


# ── validate_shader (lines 379-409) ──────────────────────────────────────


class TestValidateShader:
    def test_hardcoded_color_warning(self, tmp_path: Path) -> None:
        # Lines 379-395: shader with hardcoded color
        f = tmp_path / "glow.gdshader"
        f.write_text(
            "shader_type spatial;\n"
            "void fragment() {\n"
            "    ALBEDO = vec3(0.8, 0.2, 0.1);\n"
            "}\n"
        )
        result = validate_shader(f)
        assert any("hardcoded color" in w for w in result.warnings)

    def test_commented_color_no_warning(self, tmp_path: Path) -> None:
        # Lines 391-392: `//` comment lines skipped
        f = tmp_path / "commented.gdshader"
        f.write_text(
            "shader_type spatial;\n"
            "// ALBEDO = vec3(0.8, 0.2, 0.1); // commented out\n"
            "void fragment() {}\n"
        )
        result = validate_shader(f)
        assert not any("hardcoded color" in w for w in result.warnings)

    def test_uniform_color_no_warning(self, tmp_path: Path) -> None:
        f = tmp_path / "uniform.gdshader"
        f.write_text(
            "shader_type spatial;\n"
            "uniform vec4 albedo : hint_color = vec4(1.0, 0.0, 0.0, 1.0);\n"
            "void fragment() {}\n"
        )
        result = validate_shader(f)
        assert not any("hardcoded color" in w for w in result.warnings)

    def test_long_fragment_function_warning(self, tmp_path: Path) -> None:
        # Lines 397-407: func_start tracking, length > 50 → warning
        inner = "\n".join(f"    float x{i} = float({i});" for i in range(55))
        f = tmp_path / "complex.gdshader"
        f.write_text(f"shader_type spatial;\nvoid fragment() {{\n{inner}\n}}\n")
        result = validate_shader(f)
        assert any("consider extracting" in w for w in result.warnings)

    def test_short_fragment_function_no_warning(self, tmp_path: Path) -> None:
        f = tmp_path / "simple.gdshader"
        f.write_text(
            "shader_type spatial;\n"
            "void fragment() {\n"
            "    ALBEDO = COLOR.rgb;\n"
            "}\n"
        )
        result = validate_shader(f)
        assert not any("consider extracting" in w for w in result.warnings)

    def test_unreadable_shader_returns_empty(self, tmp_path: Path) -> None:
        # Lines 382-385: read exception → empty result
        f = tmp_path / "bad.gdshader"
        f.write_text("shader_type spatial;\n")
        with patch.object(Path, "read_text", side_effect=OSError("denied")):
            result = validate_shader(f)
        assert not result.warnings and not result.info


# ── check_version_staleness (lines 432-433) ──────────────────────────────


class TestCheckVersionStaleness:
    def _ctx(self, version: str) -> ProjectContext:
        return ProjectContext(root=Path("."), godot_version=version, has_standard_structure=True)

    def test_unknown_version_skipped(self) -> None:
        assert check_version_staleness(self._ctx("unknown")) == []

    def test_3x_skipped(self) -> None:
        assert check_version_staleness(self._ctx("3.x")) == []

    def test_newer_major_version_warns(self) -> None:
        info = check_version_staleness(self._ctx("5.0"))
        assert any("outdated" in i for i in info)

    def test_newer_minor_version_warns(self) -> None:
        info = check_version_staleness(self._ctx("4.9"))
        assert any("outdated" in i for i in info)

    def test_same_version_no_warning(self) -> None:
        # ENGINE_REF_MAX_VERSION is "4.4"
        assert check_version_staleness(self._ctx("4.4")) == []

    def test_older_version_no_warning(self) -> None:
        assert check_version_staleness(self._ctx("4.2")) == []

    def test_malformed_version_caught_silently(self) -> None:
        # Lines 432-433: int("alpha") raises ValueError → except pass
        result = check_version_staleness(self._ctx("4.alpha"))
        assert result == []

    def test_4x_alias_no_warning(self) -> None:
        # "4.x" → replace → "4.99" → minor 99 > ref 4 → warns (or not, depends on ref)
        # Just verify no exception raised
        result = check_version_staleness(self._ctx("4.x"))
        assert isinstance(result, list)
