"""Tests for consolidated hook dispatchers (on-prompt-dispatch, on-stop-dispatch, on-edit-dispatch).

Verifies:
  - Each dispatcher calls all sub-handlers
  - Individual handler failure doesn't block others
  - Timing telemetry is written to hook-timing.jsonl
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def _load_dispatcher(name: str):
    path = PLUGIN_ROOT / "packs" / "meta" / "hooks" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), str(path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPromptDispatcher:
    def test_calls_all_handlers(self, tmp_path: Path) -> None:
        mod = _load_dispatcher("on-prompt-dispatch")
        call_log: list[str] = []

        original_load = mod._load_module

        def tracking_load(name: str, path: Path):
            result = original_load(name, path)
            if result and hasattr(result, "main"):
                original_main = result.main

                def tracked_main():
                    call_log.append(name)
                    return original_main()

                result.main = tracked_main
            return result

        with patch.object(mod, "_load_module", side_effect=tracking_load):
            with patch.object(mod, "STATE_DIR", tmp_path):
                sys.stdin = io.StringIO('{"session_id": "test-dispatch"}')
                mod.main()
                sys.stdin = sys.__stdin__

        assert len(call_log) >= 3, f"Expected at least 3 handlers called, got {call_log}"

    def test_writes_timing_telemetry(self, tmp_path: Path) -> None:
        mod = _load_dispatcher("on-prompt-dispatch")

        with patch.object(mod, "STATE_DIR", tmp_path):
            sys.stdin = io.StringIO('{"session_id": "test-timing"}')
            mod.main()
            sys.stdin = sys.__stdin__

        timing_file = tmp_path / "hook-timing.jsonl"
        assert timing_file.exists()
        lines = timing_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        record = json.loads(lines[0])
        assert record["event"] == "UserPromptSubmit"
        assert "handler" in record
        assert "duration_ms" in record

    def test_handler_failure_doesnt_block_others(self, tmp_path: Path) -> None:
        mod = _load_dispatcher("on-prompt-dispatch")
        call_count = {"value": 0}

        def failing_then_working(_name: str, _path: Path):
            mock_mod = MagicMock()

            def mock_main():
                call_count["value"] += 1
                if call_count["value"] == 1:
                    raise RuntimeError("Simulated handler failure")

            mock_mod.main = mock_main
            return mock_mod

        with patch.object(mod, "_load_module", side_effect=failing_then_working):
            with patch.object(mod, "STATE_DIR", tmp_path):
                sys.stdin = io.StringIO('{"session_id": "test-failure"}')
                mod.main()
                sys.stdin = sys.__stdin__

        assert call_count["value"] >= 2, "Should continue calling after first failure"


class TestStopDispatcher:
    def test_calls_handlers(self, tmp_path: Path) -> None:
        mod = _load_dispatcher("on-stop-dispatch")

        with patch.object(mod, "STATE_DIR", tmp_path):
            sys.stdin = io.StringIO('{"session_id": "test-stop"}')
            mod.main()
            sys.stdin = sys.__stdin__

        timing_file = tmp_path / "hook-timing.jsonl"
        assert timing_file.exists()
        lines = timing_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        record = json.loads(lines[0])
        assert record["event"] == "Stop"

    def test_writes_timing_for_multiple_handlers(self, tmp_path: Path) -> None:
        mod = _load_dispatcher("on-stop-dispatch")

        with patch.object(mod, "STATE_DIR", tmp_path):
            sys.stdin = io.StringIO('{"session_id": "test-stop-timing"}')
            mod.main()
            sys.stdin = sys.__stdin__

        timing_file = tmp_path / "hook-timing.jsonl"
        lines = timing_file.read_text(encoding="utf-8").strip().split("\n")
        handlers = [json.loads(l)["handler"] for l in lines]
        assert len(handlers) >= 3, f"Expected multiple handlers, got {handlers}"


class TestEditDispatcher:
    def test_calls_handlers(self, tmp_path: Path) -> None:
        mod = _load_dispatcher("on-edit-dispatch")

        with patch.object(mod, "STATE_DIR", tmp_path):
            sys.stdin = io.StringIO('{"tool_input": {"file_path": "/tmp/test.py"}}')
            mod.main()
            sys.stdin = sys.__stdin__

        timing_file = tmp_path / "hook-timing.jsonl"
        assert timing_file.exists()
        lines = timing_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        record = json.loads(lines[0])
        assert record["event"] == "PostToolUse_Edit_Write"

    def test_empty_payload(self, tmp_path: Path) -> None:
        mod = _load_dispatcher("on-edit-dispatch")

        with patch.object(mod, "STATE_DIR", tmp_path):
            sys.stdin = io.StringIO("{}")
            mod.main()
            sys.stdin = sys.__stdin__
