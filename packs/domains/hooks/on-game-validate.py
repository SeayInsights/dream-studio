#!/usr/bin/env python3
"""Hook: on-game-validate — validate game project files on Edit|Write.

Trigger: PostToolUse on Edit|Write.

Activation: ONLY fires when the edited file is inside a Godot project,
confirmed by finding `project.godot` in an ancestor directory that also
contains at least one of: scenes/, scripts/, assets/. This prevents
false positives from stray project.godot files in parent directories.

Checks:
  1. Hardcoded gameplay values in GDScript (magic numbers in gameplay paths)
  2. Invalid JSON in data/balance files
  3. Asset naming violations (missing prefix convention)
  4. GDScript files in gameplay/ that directly reference UI nodes
  5. Missing delta multiplication in physics code
  6. Godot version staleness (project version vs engine reference coverage)

Performance: Early-exit on first check (file extension + project detection).
Typical non-game-project exit: <5ms (one stat call per ancestor dir, max 10).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain_lib.game_validate import (  # noqa: E402
    GAME_FILE_EXTENSIONS,
    MAX_WARNINGS_DISPLAYED,
    ProjectContext,
    ValidationResult,
    check_version_staleness,
    classify_path,
    detect_project,
    relative_to_project,
    validate_asset_naming,
    validate_gdscript,
    validate_json_data,
    validate_shader,
)


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        payload = {}

    file_path_str = os.environ.get("CLAUDE_FILE_PATH", "").strip()
    if not file_path_str:
        tool_input = payload.get("tool_input", {})
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except Exception:
                tool_input = {}
        file_path_str = tool_input.get("file_path", "")
    if not file_path_str:
        return

    file_path = Path(file_path_str)

    if file_path.suffix.lower() not in GAME_FILE_EXTENSIONS:
        return

    if not file_path.exists():
        return

    ctx = detect_project(file_path)
    if not ctx:
        return

    rel_path = relative_to_project(file_path, ctx.root)
    domains = classify_path(rel_path, file_path)

    all_errors: list[str] = []
    all_warnings: list[str] = []
    all_info: list[str] = []

    suffix = file_path.suffix.lower()
    if suffix == ".gd":
        r = validate_gdscript(file_path, domains)
        all_errors.extend(r.errors)
        all_warnings.extend(r.warnings)
        all_info.extend(r.info)
    elif suffix == ".json":
        r = validate_json_data(file_path, rel_path)
        all_errors.extend(r.errors)
        all_warnings.extend(r.warnings)
        all_info.extend(r.info)
    elif suffix == ".gdshader":
        r = validate_shader(file_path)
        all_errors.extend(r.errors)
        all_warnings.extend(r.warnings)
        all_info.extend(r.info)

    r = validate_asset_naming(file_path, rel_path)
    all_errors.extend(r.errors)
    all_warnings.extend(r.warnings)
    all_info.extend(r.info)

    all_info.extend(check_version_staleness(ctx))

    if not all_errors and not all_warnings and not all_info:
        return

    output_lines = [f"\n[dream-studio] Game validation — {rel_path} (Godot {ctx.godot_version})"]

    if all_errors:
        output_lines.append("  ERRORS (blocking):")
        for e in all_errors:
            output_lines.append(e)

    if all_warnings:
        output_lines.append("  Warnings:")
        shown = all_warnings[:MAX_WARNINGS_DISPLAYED]
        for w in shown:
            output_lines.append(w)
        if len(all_warnings) > MAX_WARNINGS_DISPLAYED:
            output_lines.append(f"  ... and {len(all_warnings) - MAX_WARNINGS_DISPLAYED} more warnings")

    if all_info:
        output_lines.append("  Info:")
        for info_line in all_info[:5]:
            output_lines.append(info_line)

    output_lines.append("")
    print("\n".join(output_lines), flush=True)

    if all_errors:
        sys.exit(2)


if __name__ == "__main__":
    main()
