"""Integration tests for WO-TOKEN-CAPTURE.

Covers dispatch routing (core/on-post-tool-use is the first PostToolUse handler).

TestTokenConsumptionProjection (T2 tests) removed WO-DBA-DROP (migration 137):
core/projections/token_projection.py and the token_usage_records table it
materialized into were both retired — the DuckDB aggregate_metrics.db
token_usage_records view over events_fact is the read side now.

The normalize_stop / session-accumulator tests (T3) were removed with
WO-FILESDB-REVET: the token.consumption.recorded rollup and its
raw_session_token_accumulators backing were retired (verified noise; session
totals derive from token.consumed via the DuckDB view).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


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
