"""Integration tests for WO-TOKEN-CAPTURE.

Verifies that normalize_stop falls back to the per-session accumulator
written by token_capture.handle_post_tool_use.

TestTokenConsumptionProjection (T2 tests) removed WO-DBA-DROP (migration 137):
core/projections/token_projection.py and the token_usage_records table it
materialized into were both retired — the DuckDB aggregate_metrics.db
token_usage_records view over events_fact is the read side now.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ── T3: normalize_stop accumulator fallback ───────────────────────────────────


class TestSessionAccumulator:
    def test_update_and_read_accumulator(self, tmp_path, monkeypatch):
        """_update_session_accumulator merges token counts; read returns the total."""
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        session_id = "acc-test-session-001"

        from core.telemetry.token_capture import _update_session_accumulator

        # Two tool calls accumulate.
        _update_session_accumulator(session_id, {"input_tokens": 100, "output_tokens": 50})
        _update_session_accumulator(session_id, {"input_tokens": 200, "output_tokens": 75})

        acc_path = tmp_path / ".dream-studio" / "state" / f"session-tokens-{session_id}.json"
        data = json.loads(acc_path.read_text(encoding="utf-8"))

        assert data["input_tokens"] == 300
        assert data["output_tokens"] == 125

    def test_accumulator_handles_cache_tokens(self, tmp_path, monkeypatch):
        """Cache creation and cache read tokens are accumulated correctly."""
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        session_id = "acc-test-session-002"

        from core.telemetry.token_capture import _update_session_accumulator

        _update_session_accumulator(
            session_id,
            {
                "input_tokens": 10,
                "output_tokens": 5,
                "cache_creation_input_tokens": 20,
                "cache_read_input_tokens": 30,
            },
        )

        acc_path = tmp_path / ".dream-studio" / "state" / f"session-tokens-{session_id}.json"
        data = json.loads(acc_path.read_text(encoding="utf-8"))

        assert data["cache_creation_input_tokens"] == 20
        assert data["cache_read_input_tokens"] == 30

    def test_normalize_stop_reads_accumulator_when_payload_empty(self, tmp_path, monkeypatch):
        """normalize_stop falls back to the session accumulator for token totals."""
        session_id = "stop-test-session-001"
        acc_dir = tmp_path / ".dream-studio" / "state"
        acc_dir.mkdir(parents=True)
        acc_path = acc_dir / f"session-tokens-{session_id}.json"
        acc_path.write_text(
            json.dumps({"input_tokens": 400, "output_tokens": 120}), encoding="utf-8"
        )

        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        import unittest.mock as mock

        with (
            mock.patch(
                "emitters.claude_code.emitter.get_or_create_session_id", return_value=session_id
            ),
            mock.patch("emitters.claude_code.emitter.get_active_project_id", return_value=None),
            mock.patch("emitters.claude_code.emitter._get_db_path", return_value=None),
        ):
            from emitters.claude_code.emitter import normalize_stop

            # Stop payload with no usage field.
            envelopes = normalize_stop({})

        assert len(envelopes) == 1
        payload = envelopes[0].payload
        assert payload.get("input_tokens") == 400
        assert payload.get("output_tokens") == 120

    def test_normalize_stop_prefers_payload_tokens_over_accumulator(self, tmp_path, monkeypatch):
        """normalize_stop uses Stop payload tokens when present, ignores accumulator."""
        session_id = "stop-test-session-002"
        acc_dir = tmp_path / ".dream-studio" / "state"
        acc_dir.mkdir(parents=True)
        (acc_dir / f"session-tokens-{session_id}.json").write_text(
            json.dumps({"input_tokens": 999, "output_tokens": 999}), encoding="utf-8"
        )

        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        import unittest.mock as mock

        with (
            mock.patch(
                "emitters.claude_code.emitter.get_or_create_session_id", return_value=session_id
            ),
            mock.patch("emitters.claude_code.emitter.get_active_project_id", return_value=None),
            mock.patch("emitters.claude_code.emitter._get_db_path", return_value=None),
        ):
            from emitters.claude_code.emitter import normalize_stop

            envelopes = normalize_stop({"usage": {"input_tokens": 50, "output_tokens": 30}})

        payload = envelopes[0].payload
        assert payload["input_tokens"] == 50
        assert payload["output_tokens"] == 30


# ── T1: dispatch routing includes core/on-post-tool-use ──────────────────────


def _load_dispatch_hooks():
    """Import the canonical dispatch module, ``runtime/dispatch/hooks.py``.

    Use the fully-qualified ``runtime.dispatch.hooks`` name — NOT a bare
    ``import hooks``, which resolves to the top-level ``hooks/`` namespace package
    (no ``_resolve_handlers``) and, once cached in ``sys.modules`` by an earlier
    test, shadows any ``sys.path`` insertion. The canonical module is the verbatim
    source the installer copies to ``.claude/hooks/dispatch/hooks.py`` (which is
    generated/gitignored and absent in a fresh checkout — full-ci #360 post-merge
    hit FileNotFoundError loading that path).
    """
    import runtime.dispatch.hooks as dispatch_hooks  # noqa: PLC0415

    return dispatch_hooks


class TestDispatchHookRouting:
    def test_post_tool_use_includes_token_capture_handler(self):
        """_resolve_handlers returns core/on-post-tool-use as first PostToolUse handler."""
        from pathlib import Path as _Path  # noqa: PLC0415

        dispatch_hooks = _load_dispatch_hooks()
        fake_root = _Path("/fake/plugin-root")
        handlers = dispatch_hooks._resolve_handlers("PostToolUse", "Bash", fake_root)
        names = [name for name, _ in handlers]
        assert (
            "on-post-tool-use" in names
        ), f"core/on-post-tool-use missing from PostToolUse handlers; got: {names}"
        assert (
            names[0] == "on-post-tool-use"
        ), f"on-post-tool-use must be first handler; got: {names}"

    def test_post_tool_use_skill_still_gets_skill_handlers(self):
        """Skill tool still gets on-skill-metrics and on-skill-complete in addition to token capture."""
        from pathlib import Path as _Path  # noqa: PLC0415

        dispatch_hooks = _load_dispatch_hooks()
        fake_root = _Path("/fake/plugin-root")
        handlers = dispatch_hooks._resolve_handlers("PostToolUse", "Skill", fake_root)
        names = [name for name, _ in handlers]
        assert "on-post-tool-use" in names
        assert "on-skill-metrics" in names
        assert "on-skill-complete" in names
