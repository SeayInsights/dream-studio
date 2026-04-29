"""Tests for hooks/lib/pack_context.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib import pack_context  # noqa: E402


class TestIsPackActive:
    def test_no_active_packs_all_active(self) -> None:
        with patch("lib.pack_context.state.read_config", return_value={}):
            assert pack_context.is_pack_active("meta") is True

    def test_empty_active_packs_all_active(self) -> None:
        with patch("lib.pack_context.state.read_config", return_value={"active_packs": []}):
            assert pack_context.is_pack_active("meta") is True

    def test_pack_in_list_is_active(self) -> None:
        with patch(
            "lib.pack_context.state.read_config",
            return_value={"active_packs": ["meta", "quality"]},
        ):
            assert pack_context.is_pack_active("meta") is True

    def test_pack_not_in_list_is_inactive(self) -> None:
        with patch(
            "lib.pack_context.state.read_config",
            return_value={"active_packs": ["meta"]},
        ):
            assert pack_context.is_pack_active("security") is False

    def test_config_read_error_fails_open(self) -> None:
        with patch("lib.pack_context.state.read_config", side_effect=OSError("no config")):
            assert pack_context.is_pack_active("any") is True
