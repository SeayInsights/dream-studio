"""Game validation orchestrator — extracted from on-game-validate hook."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple, Optional

from . import game_validate


class ValidationOutput(NamedTuple):
    """Result of validation with formatted output."""

    output: str
    should_block: bool


def validate_and_format(file_path: Path) -> Optional[ValidationOutput]:
    """Orchestrate validation and format output for a game file.

    Returns None if no validation needed (not a game file, no issues found).
    Returns ValidationOutput with formatted message and block flag otherwise.
    """
    if file_path.suffix.lower() not in game_validate.GAME_FILE_EXTENSIONS:
        return None

    if not file_path.exists():
        return None

    ctx = game_validate.detect_project(file_path)
    if not ctx:
        return None

    rel_path = game_validate.relative_to_project(file_path, ctx.root)
    domains = game_validate.classify_path(rel_path, file_path)

    all_errors: list[str] = []
    all_warnings: list[str] = []
    all_info: list[str] = []

    suffix = file_path.suffix.lower()
    if suffix == ".gd":
        r = game_validate.validate_gdscript(file_path, domains)
        all_errors.extend(r.errors)
        all_warnings.extend(r.warnings)
        all_info.extend(r.info)
    elif suffix == ".json":
        r = game_validate.validate_json_data(file_path, rel_path)
        all_errors.extend(r.errors)
        all_warnings.extend(r.warnings)
        all_info.extend(r.info)
    elif suffix == ".gdshader":
        r = game_validate.validate_shader(file_path)
        all_errors.extend(r.errors)
        all_warnings.extend(r.warnings)
        all_info.extend(r.info)

    r = game_validate.validate_asset_naming(file_path, rel_path)
    all_errors.extend(r.errors)
    all_warnings.extend(r.warnings)
    all_info.extend(r.info)

    all_info.extend(game_validate.check_version_staleness(ctx))

    if not all_errors and not all_warnings and not all_info:
        return None

    output_lines = [f"\n[dream-studio] Game validation — {rel_path} (Godot {ctx.godot_version})"]

    if all_errors:
        output_lines.append("  ERRORS (blocking):")
        for e in all_errors:
            output_lines.append(e)

    if all_warnings:
        output_lines.append("  Warnings:")
        shown = all_warnings[: game_validate.MAX_WARNINGS_DISPLAYED]
        for w in shown:
            output_lines.append(w)
        if len(all_warnings) > game_validate.MAX_WARNINGS_DISPLAYED:
            output_lines.append(
                f"  ... and {len(all_warnings) - game_validate.MAX_WARNINGS_DISPLAYED} more warnings"
            )

    if all_info:
        output_lines.append("  Info:")
        for info_line in all_info[:5]:
            output_lines.append(info_line)

    output_lines.append("")
    return ValidationOutput("\n".join(output_lines), bool(all_errors))
