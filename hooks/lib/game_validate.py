"""Game file validation — pure logic extracted from on-game-validate handler.

Public surface: ProjectContext, ValidationResult, detect_project, classify_path,
validate_gdscript, validate_json_data, validate_asset_naming, validate_shader,
relative_to_project, check_version_staleness.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import NamedTuple, Optional

# --- Configuration ---

MAX_ANCESTOR_DEPTH = 10
MAX_WARNINGS_DISPLAYED = 15
ENGINE_REF_MAX_VERSION = "4.4"
MAX_VALIDATE_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

GAMEPLAY_KEYWORDS = {"gameplay", "systems", "mechanics", "combat", "movement", "abilities", "mobs", "player", "characters"}
AI_KEYWORDS = {"ai", "npc", "enemies", "behavior", "behaviour", "mobs", "pathfinding", "btree"}
UI_KEYWORDS = {"ui", "hud", "menu", "gui", "interface", "menus", "dialog", "dialogs", "screens", "inventory"}
NETWORKING_KEYWORDS = {"networking", "multiplayer", "net", "network", "online", "rpc", "replication"}

GAME_FILE_EXTENSIONS = {".gd", ".json", ".glb", ".gltf", ".tres", ".tscn", ".gdshader"}

ASSET_PREFIXES = frozenset({
    "chr_", "prop_", "arch_", "ter_", "veh_",
    "vfx_", "col_", "lod1_", "lod2_",
})

HARDCODED_PATTERNS = [
    (re.compile(r'\bconst\s+\w+\s*=\s*\d+\.?\d*'),
     "const with magic number — use balance.json or exported Resource"),
    (re.compile(
        r'(?<!\w)(?:damage|speed|health|mana|cooldown|cost|range|radius|'
        r'duration|attack_power|defense|armor|max_hp|max_mp|move_speed|'
        r'fire_rate|reload_time|spawn_rate|xp_reward|gold_reward)\s*=\s*\d',
        re.IGNORECASE),
     "gameplay value appears hardcoded — load from data file or Resource"),
]

UI_REFERENCE_PATTERNS = [
    re.compile(r'\$.*(?:Label|Button|Panel|HBox|VBox|Container|TextureRect|ProgressBar|LineEdit|TextEdit|RichTextLabel|OptionButton|CheckBox|SpinBox)'),
    re.compile(r'get_node\(["\'].*(?:UI|HUD|Menu|Label|Button|Panel|Dialog)'),
    re.compile(r'(?:preload|load)\(["\']res://(?:scenes|ui)/(?:ui|hud|menu)/'),
]

VELOCITY_PATTERN = re.compile(r'\bvelocity(?:\.\w+)?\s*[+\-*/]?=.*(?:SPEED|speed|gravity|GRAVITY|acceleration|ACCELERATION)')
FUNC_PATTERN = re.compile(r'^(?:func|static func)\s')

IGNORE_FILE_PRAGMA = "# ds:ignore-file"
IGNORE_LINE_PRAGMA = "# ds:ignore"
IGNORE_NEXT_PRAGMA = "# ds:ignore-next-line"


def _is_suppressed(lines: list[str], line_idx: int) -> bool:
    """Check if a line has a suppression pragma (on the line or the line above)."""
    line = lines[line_idx]
    if IGNORE_LINE_PRAGMA in line:
        return True
    if line_idx > 0 and IGNORE_NEXT_PRAGMA in lines[line_idx - 1]:
        return True
    return False


class ProjectContext(NamedTuple):
    root: Path
    godot_version: str
    has_standard_structure: bool


class ValidationResult(NamedTuple):
    errors: list[str]
    warnings: list[str]
    info: list[str]


def detect_project(file_path: Path) -> Optional[ProjectContext]:
    """Find the Godot project root with structural validation.

    Returns None if:
    - No project.godot found within MAX_ANCESTOR_DEPTH
    - The project.godot directory lacks 2+ game project markers (scenes/, scripts/, assets/, src/, addons/)
    - The file is inside the plugin cache (not a user project)
    - The candidate root is at or above the user's home directory
    """
    normalized = str(file_path).replace("\\", "/").lower()
    if ".claude/plugins/cache" in normalized:
        return None
    if ".dream-studio" in normalized:
        return None

    home = Path.home().resolve()
    current = file_path.parent.resolve()
    for _ in range(MAX_ANCESTOR_DEPTH):
        if current == home or current == home.parent or current == current.parent:
            break

        godot_file = current / "project.godot"
        if godot_file.exists():
            markers = ["scenes", "scripts", "assets", "src", "addons"]
            marker_count = sum(1 for m in markers if (current / m).is_dir())
            if marker_count < 2:
                current = current.parent
                continue

            version = _parse_godot_version(godot_file)
            standard = (current / "scripts").is_dir() and (current / "scenes").is_dir()
            return ProjectContext(
                root=current,
                godot_version=version,
                has_standard_structure=standard,
            )
        current = current.parent
    return None


def _parse_godot_version(godot_file: Path) -> str:
    """Extract Godot version from project.godot [application] config_version or features."""
    try:
        text = godot_file.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            if line.startswith("config/features"):
                match = re.search(r'"(\d+\.\d+(?:\.\d+)?)"', line)
                if match:
                    return match.group(1)
        config_match = re.search(r'config_version\s*=\s*(\d+)', text)
        if config_match:
            cv = int(config_match.group(1))
            if cv == 5:
                return "4.x"
            elif cv == 4:
                return "3.x"
    except Exception:
        pass
    return "unknown"


def relative_to_project(file_path: Path, project_root: Path) -> str:
    try:
        return str(file_path.resolve().relative_to(project_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(file_path).replace("\\", "/")


def classify_path(rel_path: str, file_path: Optional[Path] = None) -> set[str]:
    """Classify a file path into domain categories.

    Primary: match directory names against keyword sets.
    Fallback: if no path match and file is .gd, peek at content for domain signals.
    """
    parts = set(rel_path.lower().replace("\\", "/").split("/"))
    if file_path:
        stem_parts = set(file_path.stem.lower().replace("-", "_").split("_"))
        parts = parts | stem_parts

    domains: set[str] = set()
    if parts & GAMEPLAY_KEYWORDS:
        domains.add("gameplay")
    if parts & AI_KEYWORDS:
        domains.add("ai")
    if parts & UI_KEYWORDS:
        domains.add("ui")
    if parts & NETWORKING_KEYWORDS:
        domains.add("networking")

    if not domains and file_path and file_path.suffix.lower() == ".gd":
        try:
            head = file_path.read_text(encoding="utf-8", errors="ignore")[:2000]
            if any(kw in head for kw in ("CharacterBody2D", "CharacterBody3D", "move_and_slide", "velocity")):
                domains.add("gameplay")
            if any(kw in head for kw in ("NavigationAgent", "AStarGrid", "behavior_tree", "state_machine")):
                domains.add("ai")
            if any(kw in head for kw in ("Control", "Panel", "Label", "Button", "HBoxContainer", "VBoxContainer")):
                domains.add("ui")
            if any(kw in head for kw in ("@rpc", "multiplayer", "MultiplayerAPI", "MultiplayerSpawner")):
                domains.add("networking")
        except Exception:
            pass

    return domains


def validate_gdscript(file_path: Path, domains: set[str]) -> ValidationResult:
    """Validate a .gd file for game code issues."""
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    try:
        if file_path.stat().st_size > MAX_VALIDATE_FILE_SIZE:
            return ValidationResult([], [], [f"  Skipped: file too large (>{MAX_VALIDATE_FILE_SIZE // 1024 // 1024}MB)"])
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return ValidationResult([f"  Could not read file: {e}"], [], [])

    lines = content.splitlines()

    if any(IGNORE_FILE_PRAGMA in line for line in lines[:5]):
        return ValidationResult(errors, warnings, info)

    is_gameplay = "gameplay" in domains
    is_ai = "ai" in domains
    is_ui = "ui" in domains
    is_net = "networking" in domains

    # --- Check 1: Hardcoded gameplay values ---
    if is_gameplay or is_ai:
        hardcoded_count = 0
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            if _is_suppressed(lines, i - 1):
                continue
            if stripped.startswith(("enum ", "signal ", "class_name ")):
                continue
            if "@export" in line:
                continue
            for pattern, msg in HARDCODED_PATTERNS:
                if pattern.search(line):
                    hardcoded_count += 1
                    if hardcoded_count <= 5:
                        warnings.append(f"  Line {i}: {msg}")
                    break
        if hardcoded_count > 5:
            warnings.append(f"  ... {hardcoded_count - 5} more hardcoded values")

    # --- Check 2: UI references in gameplay code ---
    if is_gameplay:
        ui_ref_count = 0
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _is_suppressed(lines, i - 1):
                continue
            for pattern in UI_REFERENCE_PATTERNS:
                if pattern.search(line):
                    ui_ref_count += 1
                    if ui_ref_count <= 3:
                        warnings.append(f"  Line {i}: gameplay code references UI — emit signals instead")
                    break
        if ui_ref_count > 3:
            warnings.append(f"  ... {ui_ref_count - 3} more UI references in gameplay code")

    # --- Check 3: Missing delta in physics ---
    if is_gameplay or is_ai:
        current_func = ""
        in_physics_func = False
        for i, line in enumerate(lines, 1):
            if FUNC_PATTERN.match(line.strip()):
                current_func = line.strip()
                in_physics_func = "_physics_process" in current_func or "_process" in current_func
            if in_physics_func and VELOCITY_PATTERN.search(line):
                if "delta" not in line.lower() and not _is_suppressed(lines, i - 1):
                    warnings.append(f"  Line {i}: velocity change in {current_func.split('(')[0].replace('func ', '')} — missing delta?")

    # --- Check 4: Networking anti-patterns ---
    if is_net:
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r'\.position\s*=', line) and "is_multiplayer_authority" not in content[:content.find(line)]:
                if "set_position" not in line and "@rpc" not in line:
                    info.append(f"  Line {i}: direct position set in network code — verify authority check exists")
            if "@rpc" in line and "any_peer" in line:
                info.append(f"  Line {i}: @rpc(any_peer) — ensure server validates all data from this RPC")

    # --- Check 5: UI code owning game state ---
    if is_ui:
        state_mutations = re.compile(
            r'(?:GameState|game_state|PlayerData|player_data)\.\w+\s*[+\-*/]?='
        )
        for i, line in enumerate(lines, 1):
            if state_mutations.search(line):
                warnings.append(f"  Line {i}: UI code mutating game state — use signals or autoload methods")

    return ValidationResult(errors, warnings, info)


def validate_json_data(file_path: Path, rel_path: str) -> ValidationResult:
    """Validate JSON data files with schema consistency checks."""
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return ValidationResult(["  Could not read file"], [], [])

    if not text.strip():
        return ValidationResult(["  INVALID JSON: file is empty"], [], [])

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return ValidationResult([f"  INVALID JSON at line {e.lineno}, col {e.colno}: {e.msg}"], [], [])

    is_balance = "balance" in rel_path.lower()
    is_data_dir = any(seg in rel_path.lower() for seg in ("data/", "design/balance"))

    if is_balance:
        def check_values(obj: object, path: str = "") -> list[str]:
            issues: list[str] = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    issues.extend(check_values(v, f"{path}.{k}"))
            elif isinstance(obj, list):
                for idx, v in enumerate(obj):
                    issues.extend(check_values(v, f"{path}[{idx}]"))
            elif isinstance(obj, (int, float)):
                if abs(obj) > 999999 and "id" not in path.lower() and "seed" not in path.lower():
                    issues.append(f"  {path}: value {obj} seems extreme — verify intentional")
                if isinstance(obj, float) and (obj != obj):  # NaN check
                    issues.append(f"  {path}: NaN value detected")
            return issues
        warnings.extend(check_values(data))

    if isinstance(data, dict) and len(data) > 2:
        bad_keys = [k for k in data.keys() if k != k.lower() and not k.startswith("_") and not k.isupper()]
        if bad_keys and len(bad_keys) > len(data) * 0.3:
            warnings.append(f"  Keys should be snake_case (found: {', '.join(bad_keys[:3])}{'...' if len(bad_keys) > 3 else ''})")

    if isinstance(data, dict) and is_data_dir:
        for key, val in data.items():
            if isinstance(val, list) and len(val) >= 2 and all(isinstance(v, dict) for v in val):
                key_sets = [set(v.keys()) for v in val]
                reference = key_sets[0]
                for idx, ks in enumerate(key_sets[1:], 1):
                    missing = reference - ks
                    extra = ks - reference
                    if missing:
                        warnings.append(f"  {key}[{idx}] missing keys vs [0]: {', '.join(sorted(missing))}")
                        break
                    if extra:
                        info.append(f"  {key}[{idx}] has extra keys vs [0]: {', '.join(sorted(extra))}")
                        break

    return ValidationResult(errors, warnings, info)


def validate_asset_naming(file_path: Path, rel_path: str) -> ValidationResult:
    """Check asset file naming conventions."""
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    if file_path.suffix.lower() not in {".glb", ".gltf", ".tres", ".tscn"}:
        return ValidationResult(errors, warnings, info)

    if not any(seg in rel_path.lower() for seg in ("assets/", "art/", "models/", "meshes/")):
        return ValidationResult(errors, warnings, info)

    name = file_path.name
    stem = file_path.stem.lower()

    if file_path.suffix.lower() in {".glb", ".gltf"}:
        if not any(stem.startswith(prefix) for prefix in ASSET_PREFIXES):
            valid = ", ".join(sorted(ASSET_PREFIXES))
            warnings.append(f"  '{name}' missing type prefix (expected one of: {valid})")

    if " " in name:
        errors.append(f"  '{name}' contains spaces — use snake_case (Godot import breaks with spaces in some contexts)")

    if name != name.lower() and not name.endswith((".tres", ".tscn")):
        warnings.append(f"  '{name}' should be lowercase")

    return ValidationResult(errors, warnings, info)


def validate_shader(file_path: Path) -> ValidationResult:
    """Basic shader validation."""
    warnings: list[str] = []
    info: list[str] = []

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return ValidationResult([], [], [])

    lines = content.splitlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        if re.search(r'(?:color|albedo|emission)\s*=\s*vec[34]\([\d.]+', line, re.IGNORECASE):
            if "uniform" not in line:
                warnings.append(f"  Line {i}: hardcoded color/visual value — use a uniform with hint_color or hint_range")

    func_start = None
    func_name = ""
    for i, line in enumerate(lines, 1):
        if re.match(r'^void\s+(vertex|fragment|light)\s*\(', line.strip()):
            func_start = i
            func_name = line.strip().split("(")[0].split()[-1]
        elif func_start and line.strip() == "}":
            length = i - func_start
            if length > 50:
                warnings.append(f"  {func_name}() is {length} lines — consider extracting to helper functions (<50 lines recommended)")
            func_start = None

    return ValidationResult([], warnings, info)


def check_version_staleness(ctx: ProjectContext) -> list[str]:
    """Warn if project Godot version exceeds engine reference coverage."""
    info: list[str] = []
    ver = ctx.godot_version
    if ver in ("unknown", "3.x"):
        return info

    try:
        parts = ver.replace("4.x", "4.99").split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        ref_parts = ENGINE_REF_MAX_VERSION.split(".")
        ref_major = int(ref_parts[0])
        ref_minor = int(ref_parts[1])

        if major > ref_major or (major == ref_major and minor > ref_minor):
            info.append(
                f"  Engine reference covers Godot {ENGINE_REF_MAX_VERSION}. "
                f"Project uses {ver}. Some API guidance may be outdated."
            )
    except (ValueError, IndexError):
        pass
    return info
