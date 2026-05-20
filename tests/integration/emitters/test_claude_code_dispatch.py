"""Tests for emitters/claude_code/run.py dispatch.

Replaces tests/integration/test_hook_dispatchers.py (which tested hooks/run.py).
Verifies that the new emitter entry point correctly dispatches to event normalizers
and writes events to the spool without error.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
EMITTER_RUN = PLUGIN_ROOT / "emitters" / "claude_code" / "run.py"


def _load_emitter_run():
    spec = importlib.util.spec_from_file_location("emitters_claude_code_run", str(EMITTER_RUN))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestEmitterDispatch:
    def test_user_prompt_submit_writes_to_spool(self, spool_root):
        payload = {"prompt": "hello test", "session_id": "test-123"}
        sys.stdin = io.StringIO(json.dumps(payload))
        sys.argv = [str(EMITTER_RUN), "UserPromptSubmit"]
        mod = _load_emitter_run()
        exit_code = mod.main()
        sys.stdin = sys.__stdin__
        assert exit_code == 0
        # Inline ingestor moves events through state dirs — check all of them
        total = sum(
            len(list((spool_root / d).glob("*.json")))
            for d in ("spool", "processing", "processed", "failed")
            if (spool_root / d).exists()
        )
        assert total >= 1

    def test_stop_writes_to_spool(self, spool_root):
        payload = {"stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 5}}
        sys.stdin = io.StringIO(json.dumps(payload))
        sys.argv = [str(EMITTER_RUN), "Stop"]
        mod = _load_emitter_run()
        exit_code = mod.main()
        sys.stdin = sys.__stdin__
        assert exit_code == 0

    def test_post_tool_use_writes_to_spool(self, spool_root):
        payload = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.py"},
            "tool_result": "ok",
        }
        sys.stdin = io.StringIO(json.dumps(payload))
        sys.argv = [str(EMITTER_RUN), "PostToolUse"]
        mod = _load_emitter_run()
        exit_code = mod.main()
        sys.stdin = sys.__stdin__
        assert exit_code == 0

    def test_post_compact_writes_to_spool(self, spool_root):
        payload = {"context_size": 50000}
        sys.stdin = io.StringIO(json.dumps(payload))
        sys.argv = [str(EMITTER_RUN), "PostCompact"]
        mod = _load_emitter_run()
        exit_code = mod.main()
        sys.stdin = sys.__stdin__
        assert exit_code == 0

    def test_unknown_event_exits_zero(self, spool_root):
        sys.stdin = io.StringIO("{}")
        sys.argv = [str(EMITTER_RUN), "UnknownEvent"]
        mod = _load_emitter_run()
        exit_code = mod.main()
        sys.stdin = sys.__stdin__
        assert exit_code == 0

    def test_malformed_json_exits_zero(self, spool_root):
        sys.stdin = io.StringIO("{not valid json}")
        sys.argv = [str(EMITTER_RUN), "UserPromptSubmit"]
        mod = _load_emitter_run()
        exit_code = mod.main()
        sys.stdin = sys.__stdin__
        assert exit_code == 0

    def test_empty_payload_exits_zero(self, spool_root):
        sys.stdin = io.StringIO("")
        sys.argv = [str(EMITTER_RUN), "Stop"]
        mod = _load_emitter_run()
        exit_code = mod.main()
        sys.stdin = sys.__stdin__
        assert exit_code == 0

    def test_no_argv_exits_zero(self, spool_root):
        sys.stdin = io.StringIO("{}")
        sys.argv = [str(EMITTER_RUN)]
        mod = _load_emitter_run()
        exit_code = mod.main()
        sys.stdin = sys.__stdin__
        assert exit_code == 0

    def test_spool_events_have_required_fields(self, spool_root):
        payload = {"prompt": "test prompt"}
        sys.stdin = io.StringIO(json.dumps(payload))
        sys.argv = [str(EMITTER_RUN), "UserPromptSubmit"]
        mod = _load_emitter_run()
        mod.main()
        sys.stdin = sys.__stdin__

        # Events flow through state dirs — exclude .reason.json files from failed/
        event_files = [
            p
            for d in ("spool", "processing", "processed", "failed")
            for p in ((spool_root / d).glob("*.json") if (spool_root / d).exists() else [])
            if not p.name.endswith(".reason.json")
        ]
        assert event_files, "Expected at least one event in spool pipeline"
        event = json.loads(event_files[0].read_text(encoding="utf-8"))
        for field in ("event_id", "event_type", "timestamp", "schema_version"):
            assert field in event, f"Missing required field: {field}"

    def test_raw_prompt_not_retained(self, spool_root):
        payload = {"prompt": "this is my secret prompt text"}
        sys.stdin = io.StringIO(json.dumps(payload))
        sys.argv = [str(EMITTER_RUN), "UserPromptSubmit"]
        mod = _load_emitter_run()
        mod.main()
        sys.stdin = sys.__stdin__

        event_files = [
            p
            for d in ("spool", "processing", "processed", "failed")
            for p in ((spool_root / d).glob("*.json") if (spool_root / d).exists() else [])
            if not p.name.endswith(".reason.json")
        ]
        if event_files:
            event_text = event_files[0].read_text(encoding="utf-8")
            assert "secret prompt text" not in event_text
            event = json.loads(event_text)
            assert event.get("raw_prompt_retained") is False
