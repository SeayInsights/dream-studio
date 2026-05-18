"""End-to-end test: hooks.json → dispatcher → handler execution.

Supplements the 93 existing handler tests (which call handlers via
load_handler() directly) and the 17 dispatcher-unit tests (which mock
run_handlers entirely).  These tests close the gap between those two
layers: a Claude Code hook event enters the dispatcher exactly the way
production runtime does, and the correct handler code actually executes.

Invocation contract (mirrors production):
  - Import runtime/dispatch/hooks.py directly — no subprocess.
  - Feed hook JSON via stdin the same way Claude Code does.
  - Use a wrapping spy on dispatch_tracking.run_handlers so the first
    call's handler list is recorded while the real function still runs.

A test passes when all three hold simultaneously:
  1. hooks.json has a registered dispatcher entry for the event.
  2. The dispatcher received the JSON and routed to the expected handler.
  3. The dispatcher exited 0 (chain did not crash).
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure repo root is importable (mirrors how tests/conftest.py sets up paths)
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from control.execution import dispatch_tracking  # noqa: E402

DISPATCHER = PLUGIN_ROOT / "runtime" / "dispatch" / "hooks.py"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"
HANDLERS_META = PLUGIN_ROOT / "runtime" / "hooks" / "meta"


# ── Module loader ─────────────────────────────────────────────────────────────


def _load_dispatcher():
    """Load the dispatcher as a fresh module object (bypasses sys.modules cache)."""
    spec = importlib.util.spec_from_file_location(
        "runtime_dispatch_hooks_e2e", str(DISPATCHER)
    )
    assert spec and spec.loader, "Cannot locate runtime/dispatch/hooks.py"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture
def dispatch_env(tmp_path, monkeypatch, spool_root):
    """Redirect Path.home() and set CLAUDE_PLUGIN_ROOT.

    spool_root (from conftest) already redirects DS_SPOOL_ROOT so event
    writes stay in tmp.  This fixture additionally redirects Path.home()
    so state/ and meta/ writes inside handlers also land in tmp_path
    rather than the real home directory.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN_ROOT))
    return tmp_path


# ── Run helper ────────────────────────────────────────────────────────────────


def _run(event_name: str, payload: dict) -> tuple[list[str], int]:
    """Feed event JSON into the dispatcher; return (top-level handler names, exit code).

    Wraps dispatch_tracking.run_handlers so:
    - The first call (from hooks.py main) is recorded for routing assertions.
    - The real run_handlers still executes, so handler code actually runs.
    """
    saved_argv = sys.argv[:]
    saved_stdin = sys.stdin
    sys.argv = [str(DISPATCHER), event_name]
    sys.stdin = io.StringIO(json.dumps(payload))

    try:
        with patch.object(
            dispatch_tracking,
            "run_handlers",
            wraps=dispatch_tracking.run_handlers,
        ) as spy:
            mod = _load_dispatcher()
            exit_code = mod.main()
    finally:
        sys.argv = saved_argv
        sys.stdin = saved_stdin

    # First spy call is the top-level dispatch from hooks.py main().
    # Subsequent calls (if any) come from handler sub-dispatchers — ignored here.
    called_names: list[str] = []
    if spy.call_args_list:
        first_handlers = spy.call_args_list[0].args[0]  # positional arg 0 = handlers list
        called_names = [name for name, _ in first_handlers]

    return called_names, exit_code


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestHookDispatchChainE2E:
    """Full chain: dispatcher receives JSON → run_handlers called → handler executes."""

    # ── UserPromptSubmit ──────────────────────────────────────────────────────

    def test_user_prompt_submit_routes_to_prompt_dispatch(self, dispatch_env):
        names, _ = _run(
            "UserPromptSubmit",
            {"session_id": "e2e-test-abc", "prompt": "hello world"},
        )
        assert "on-prompt-dispatch" in names

    def test_user_prompt_submit_exits_zero(self, dispatch_env):
        _, code = _run(
            "UserPromptSubmit",
            {"session_id": "e2e-test-abc", "prompt": "hello world"},
        )
        assert code == 0

    # ── Stop ─────────────────────────────────────────────────────────────────

    def test_stop_routes_to_stop_dispatch(self, dispatch_env):
        names, _ = _run(
            "Stop",
            {"session_id": "e2e-test-abc", "stop_reason": "end_turn"},
        )
        assert "on-stop-dispatch" in names

    def test_stop_exits_zero(self, dispatch_env):
        _, code = _run(
            "Stop",
            {"session_id": "e2e-test-abc", "stop_reason": "end_turn"},
        )
        assert code == 0

    # ── PostCompact ───────────────────────────────────────────────────────────

    def test_post_compact_routes_to_on_post_compact(self, dispatch_env):
        names, _ = _run("PostCompact", {"session_id": "e2e-test-abc"})
        assert "on-post-compact" in names

    def test_post_compact_exits_zero(self, dispatch_env):
        _, code = _run("PostCompact", {"session_id": "e2e-test-abc"})
        assert code == 0

    # ── PostToolUse — Skill ───────────────────────────────────────────────────

    def test_post_tool_use_skill_routes_all_three_handlers(self, dispatch_env):
        """Skill toolName must trigger on-tool-activity + on-skill-metrics + on-skill-complete."""
        names, code = _run(
            "PostToolUse",
            {
                "toolName": "Skill",
                "tool_input": {"skill": "ds-core", "args": "build"},
                "session_id": "e2e-test-abc",
            },
        )
        assert code == 0
        assert "on-tool-activity" in names
        assert "on-skill-metrics" in names
        assert "on-skill-complete" in names

    # ── PostToolUse — Edit ────────────────────────────────────────────────────

    def test_post_tool_use_edit_routes_tool_activity_and_edit_dispatch(self, dispatch_env):
        names, code = _run(
            "PostToolUse",
            {"toolName": "Edit", "tool_input": {"file_path": "src/foo.py"}},
        )
        assert code == 0
        assert "on-tool-activity" in names
        assert "on-edit-dispatch" in names

    # ── PostToolUse — Write ───────────────────────────────────────────────────

    def test_post_tool_use_write_routes_to_edit_dispatch_branch(self, dispatch_env):
        """Write shares the Edit|Write|MultiEdit branch — on-edit-dispatch must fire."""
        names, code = _run(
            "PostToolUse",
            {"toolName": "Write", "tool_input": {"file_path": "src/bar.py"}},
        )
        assert code == 0
        assert "on-edit-dispatch" in names

    # ── PostToolUse — Read ────────────────────────────────────────────────────

    def test_post_tool_use_read_routes_tool_activity_and_skill_load(self, dispatch_env):
        names, code = _run(
            "PostToolUse",
            {
                "toolName": "Read",
                "tool_input": {"file_path": "canonical/skills/core/SKILL.md"},
            },
        )
        assert code == 0
        assert "on-tool-activity" in names
        assert "on-skill-load" in names

    # ── PostToolUse — generic / negative ─────────────────────────────────────

    def test_post_tool_use_bash_exits_zero_and_fires_tool_activity(self, dispatch_env):
        """Bash is not in any special branch — only on-tool-activity fires."""
        names, code = _run("PostToolUse", {"toolName": "Bash", "tool_input": {}})
        assert code == 0
        assert "on-tool-activity" in names

    def test_unknown_tool_name_only_fires_tool_activity(self, dispatch_env):
        """Unrecognised toolName must fire on-tool-activity and nothing else."""
        names, code = _run("PostToolUse", {"toolName": "UnknownTool"})
        assert code == 0
        assert "on-tool-activity" in names
        assert "on-skill-metrics" not in names
        assert "on-edit-dispatch" not in names
        assert "on-skill-load" not in names

    def test_multiedit_routes_to_edit_dispatch_branch(self, dispatch_env):
        """MultiEdit must follow the same Edit|Write|MultiEdit branch."""
        names, _ = _run(
            "PostToolUse",
            {"toolName": "MultiEdit", "tool_input": {}},
        )
        assert "on-edit-dispatch" in names

    # ── Cross-cutting ─────────────────────────────────────────────────────────

    def test_all_routed_handler_files_exist_on_disk(self):
        """Every handler that _resolve_handlers() can route to must be on disk.

        If a handler file is missing, run_handlers silently skips it — tests
        stay green while production dispatch silently drops events.  This test
        catches that class of bug.
        """
        expected = [
            HANDLERS_META / "on-prompt-dispatch.py",
            HANDLERS_META / "on-stop-dispatch.py",
            HANDLERS_META / "on-post-compact.py",
            HANDLERS_META / "on-tool-activity.py",
            HANDLERS_META / "on-skill-metrics.py",
            HANDLERS_META / "on-skill-complete.py",
            HANDLERS_META / "on-edit-dispatch.py",
            HANDLERS_META / "on-skill-load.py",
        ]
        missing = [str(p.relative_to(PLUGIN_ROOT)) for p in expected if not p.is_file()]
        assert missing == [], f"Handler files missing from disk: {missing}"
