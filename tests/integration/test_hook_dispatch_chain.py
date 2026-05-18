"""Integration test: hooks.json → dispatcher → handler chain.

Verifies that:
1. hooks.json registers the runtime dispatcher alongside the emitter for every event.
2. The dispatcher routes each event to the correct handler(s).
3. PostToolUse routing selects additional handlers based on toolName.
4. The dispatcher always exits 0, including on bad input.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"
DISPATCHER = PLUGIN_ROOT / "runtime" / "dispatch" / "hooks.py"


def _load_dispatcher():
    spec = importlib.util.spec_from_file_location("runtime_dispatch_hooks", str(DISPATCHER))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _all_commands(data: dict, event: str) -> list[str]:
    cmds = []
    for group in data["hooks"].get(event, []):
        for h in group.get("hooks", []):
            if h.get("type") == "command":
                cmds.append(h["command"])
    return cmds


class TestHooksJsonDispatcherRegistration:
    """hooks.json must register the runtime dispatcher alongside the emitter."""

    def _load(self) -> dict:
        return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))

    def _has_dispatcher(self, event: str) -> bool:
        cmds = _all_commands(self._load(), event)
        return any(
            "'runtime'/'dispatch'/'hooks.py'" in c
            or "'runtime'\\\\/'dispatch'\\\\/'hooks.py'" in c
            for c in cmds
        )

    def test_user_prompt_submit_has_dispatcher(self):
        assert self._has_dispatcher("UserPromptSubmit"), (
            "UserPromptSubmit must register runtime/dispatch/hooks.py"
        )

    def test_stop_has_dispatcher(self):
        assert self._has_dispatcher("Stop"), "Stop must register runtime/dispatch/hooks.py"

    def test_post_compact_has_dispatcher(self):
        assert self._has_dispatcher("PostCompact"), (
            "PostCompact must register runtime/dispatch/hooks.py"
        )

    def test_post_tool_use_has_dispatcher(self):
        assert self._has_dispatcher("PostToolUse"), (
            "PostToolUse must register runtime/dispatch/hooks.py"
        )

    def test_dispatcher_file_exists(self):
        assert DISPATCHER.is_file(), "runtime/dispatch/hooks.py must exist"


class TestDispatcherRouting:
    """Dispatcher routes events to correct handler scripts without executing them."""

    def _run(self, event_name: str, payload: dict, monkeypatch) -> tuple[list[str], int]:
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN_ROOT))
        sys.argv = [str(DISPATCHER), event_name]
        sys.stdin = io.StringIO(json.dumps(payload))

        invoked: list[str] = []

        def fake_run_handlers(handlers, raw_payload, event_tag, state_dir):
            invoked.extend(name for name, _ in handlers)

        with patch("control.execution.dispatch_tracking.run_handlers", side_effect=fake_run_handlers):
            mod = _load_dispatcher()
            exit_code = mod.main()

        sys.stdin = sys.__stdin__
        return invoked, exit_code

    def test_user_prompt_submit_routes_to_prompt_dispatch(self, monkeypatch):
        invoked, code = self._run("UserPromptSubmit", {"prompt": "hello"}, monkeypatch)
        assert code == 0
        assert "on-prompt-dispatch" in invoked

    def test_stop_routes_to_stop_dispatch(self, monkeypatch):
        invoked, code = self._run("Stop", {"stop_reason": "end_turn"}, monkeypatch)
        assert code == 0
        assert "on-stop-dispatch" in invoked

    def test_post_compact_routes_to_post_compact(self, monkeypatch):
        invoked, code = self._run("PostCompact", {}, monkeypatch)
        assert code == 0
        assert "on-post-compact" in invoked

    def test_post_tool_use_always_fires_tool_activity(self, monkeypatch):
        invoked, code = self._run("PostToolUse", {"toolName": "Bash"}, monkeypatch)
        assert code == 0
        assert "on-tool-activity" in invoked

    def test_post_tool_use_skill_adds_metrics_and_complete(self, monkeypatch):
        invoked, code = self._run("PostToolUse", {"toolName": "Skill"}, monkeypatch)
        assert code == 0
        assert "on-tool-activity" in invoked
        assert "on-skill-metrics" in invoked
        assert "on-skill-complete" in invoked

    def test_post_tool_use_edit_adds_edit_dispatch(self, monkeypatch):
        invoked, code = self._run("PostToolUse", {"toolName": "Edit"}, monkeypatch)
        assert code == 0
        assert "on-tool-activity" in invoked
        assert "on-edit-dispatch" in invoked

    def test_post_tool_use_write_adds_edit_dispatch(self, monkeypatch):
        invoked, code = self._run("PostToolUse", {"toolName": "Write"}, monkeypatch)
        assert code == 0
        assert "on-edit-dispatch" in invoked

    def test_post_tool_use_read_adds_skill_load(self, monkeypatch):
        invoked, code = self._run("PostToolUse", {"toolName": "Read"}, monkeypatch)
        assert code == 0
        assert "on-tool-activity" in invoked
        assert "on-skill-load" in invoked

    def test_post_tool_use_skill_does_not_fire_edit_dispatch(self, monkeypatch):
        invoked, code = self._run("PostToolUse", {"toolName": "Skill"}, monkeypatch)
        assert "on-edit-dispatch" not in invoked

    def test_unknown_event_exits_zero(self, monkeypatch):
        _, code = self._run("UnknownEvent", {}, monkeypatch)
        assert code == 0

    def test_no_argv_exits_zero(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN_ROOT))
        sys.argv = [str(DISPATCHER)]
        sys.stdin = io.StringIO("{}")
        mod = _load_dispatcher()
        code = mod.main()
        sys.stdin = sys.__stdin__
        assert code == 0

    def test_malformed_json_exits_zero(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN_ROOT))
        sys.argv = [str(DISPATCHER), "UserPromptSubmit"]
        sys.stdin = io.StringIO("{not valid json}")
        with patch("control.execution.dispatch_tracking.run_handlers"):
            mod = _load_dispatcher()
            code = mod.main()
        sys.stdin = sys.__stdin__
        assert code == 0
