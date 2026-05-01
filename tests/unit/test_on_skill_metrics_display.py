"""Unit tests for on-skill-metrics _build_display_name and backward-compat.

T004 — display_name construction logic
T005 — harvest_skill_velocity handles mixed old/new record format
"""

from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conftest import load_handler  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_helper() -> types.ModuleType:
    """Load the on-skill-metrics handler and return the module."""
    return load_handler("on-skill-metrics")


# ---------------------------------------------------------------------------
# T004 — _build_display_name
# ---------------------------------------------------------------------------

class TestBuildDisplayName:
    """Unit tests for the _build_display_name helper."""

    @pytest.fixture(autouse=True)
    def mod(self) -> types.ModuleType:
        self._mod = _get_helper()
        return self._mod

    def _fn(self, skill_name: str, skill_args: str) -> tuple[str, str | None]:
        return self._mod._build_display_name(skill_name, skill_args)

    def test_pack_only_strips_prefix(self) -> None:
        """Pack-only invocation strips dream-studio: prefix, no mode."""
        display_name, mode = self._fn("dream-studio:core", "")
        assert display_name == "core"
        assert mode is None

    def test_pack_and_mode_produces_colon_qualified_name(self) -> None:
        """Pack + mode produces 'pack:mode' display name."""
        display_name, mode = self._fn("dream-studio:core", "think")
        assert display_name == "core:think"
        assert mode == "think"

    def test_without_prefix_still_uses_mode(self) -> None:
        """Skill name without dream-studio: prefix is used as-is for the pack."""
        display_name, mode = self._fn("core", "think")
        assert display_name == "core:think"
        assert mode == "think"

    def test_empty_args_returns_no_mode(self) -> None:
        """Empty args string yields no mode component."""
        display_name, mode = self._fn("dream-studio:quality", "")
        assert display_name == "quality"
        assert mode is None

    def test_multi_word_args_uses_first_word_only(self) -> None:
        """Only the first word of args becomes the mode."""
        display_name, mode = self._fn("dream-studio:core", "build execute plan")
        assert display_name == "core:build"
        assert mode == "build"

    def test_unknown_skill_no_args(self) -> None:
        """'unknown' skill name with no args passes through unchanged."""
        display_name, mode = self._fn("unknown", "")
        assert display_name == "unknown"
        assert mode is None

    def test_whitespace_only_args_treated_as_empty(self) -> None:
        """Args consisting only of whitespace are treated as empty."""
        display_name, mode = self._fn("dream-studio:core", "   ")
        assert display_name == "core"
        assert mode is None

    def test_mode_returned_is_first_token(self) -> None:
        """Returned mode value is exactly the first token, not the full args."""
        _, mode = self._fn("dream-studio:domains", "game-dev extra")
        assert mode == "game-dev"


# ---------------------------------------------------------------------------
# T005 — harvest_skill_velocity backward compatibility
# ---------------------------------------------------------------------------

def _insert_telemetry_row(db: Path, skill_name: str) -> None:
    """Insert a minimal row directly into raw_skill_telemetry for test setup.

    harvest_skill_velocity reads from the effective_skill_runs view, which
    is backed by raw_skill_telemetry — not raw_token_usage.  We bypass the
    high-level insert_token_usage helper and write the telemetry table directly
    so the view picks up the rows.
    """
    from lib.studio_db import _connect  # noqa: E402

    with _connect(db) as c:
        c.execute(
            """INSERT INTO raw_skill_telemetry
               (skill_name, invoked_at, model, input_tokens, output_tokens, success)
               VALUES (?, datetime('now'), 'sonnet', 10, 20, 1)""",
            (skill_name,),
        )


class TestHarvestSkillVelocityBackwardCompat:
    """Verify the harvester handles mixed old (bare pack) and new (pack:mode) records."""

    def test_mixed_records_do_not_crash(self, tmp_path: Path) -> None:
        """harvest_skill_velocity groups by skill_name so old 'core' and new
        'core:think' records coexist without raising an exception.

        The effective_skill_runs view is backed by raw_skill_telemetry.  Old
        records stored bare pack names; new records store pack:mode strings.
        Both should appear as separate groups — no crash, no data loss.
        """
        from scripts.ds_analytics.harvester import harvest_skill_velocity  # noqa: E402

        db = tmp_path / "studio.db"

        # Old-format record: bare pack name written before this change
        _insert_telemetry_row(db, "core")
        # New-format record: pack:mode written after this change
        _insert_telemetry_row(db, "core:think")

        # harvest_skill_velocity must not raise
        df = harvest_skill_velocity(db_path=db)

        # Both skill names appear as separate rows, proving natural separation
        skill_names = set(df["skill_name"].tolist())
        assert "core" in skill_names, "Old-format 'core' records should appear"
        assert "core:think" in skill_names, "New-format 'core:think' records should appear"

    def test_empty_db_returns_correct_columns(self, tmp_path: Path) -> None:
        """Empty database returns DataFrame with expected columns, not an exception."""
        from lib.studio_db import _connect  # noqa: E402
        from scripts.ds_analytics.harvester import harvest_skill_velocity  # noqa: E402

        db = tmp_path / "empty.db"
        # Create schema only (no rows)
        _connect(db).close()

        df = harvest_skill_velocity(db_path=db)
        assert list(df.columns) == ["skill_name", "week", "invocation_count", "success_rate"]
        assert len(df) == 0
