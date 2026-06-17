"""Unit tests for context-threshold scaling (WO-CONTEXT-THRESHOLD-SCALE).

The KB-fallback handoff/compact thresholds were tuned for a 200k-token window and
tripped at ~50% on the opus-4-8[1m] (1M-token) model, creating false 'compact now'
pressure and premature auto-handoff drafts. The thresholds are now scaled to the
active context window (env DREAM_STUDIO_CONTEXT_WINDOW_TOKENS > ds_config
'context.window_tokens' > 200k baseline).

Tests:
  T1 — test_threshold_scales_with_model_window
  T2 — test_no_premature_handoff_on_1m_model
  T3 — test_end_to_end
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

ENV = "DREAM_STUDIO_CONTEXT_WINDOW_TOKENS"


@pytest.fixture
def fresh_db(tmp_path: Path) -> Path:
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db)
    return db


# ---------------------------------------------------------------------------
# T1 — thresholds scale with the active model's context window
# ---------------------------------------------------------------------------


def test_threshold_scales_with_model_window(
    fresh_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The KB thresholds scale linearly with the active context window: 1.0 at the
    200k baseline, 5.0 on the 1M model.

    AC: tests/unit/test_context_threshold.py::test_threshold_scales_with_model_window
    """
    from control.context.handoff import (
        BASELINE_WINDOW_TOKENS,
        HANDOFF_KB,
        context_window_tokens,
        kb_threshold_scale,
        scaled_kb_thresholds,
    )

    monkeypatch.delenv(ENV, raising=False)

    # Baseline: no env, no ds_config row → 200k, scale 1.0, thresholds unchanged.
    assert context_window_tokens(db_path=fresh_db) == BASELINE_WINDOW_TOKENS
    assert kb_threshold_scale(db_path=fresh_db) == 1.0
    assert scaled_kb_thresholds(db_path=fresh_db)["handoff"] == HANDOFF_KB

    # ds_config override (no env): 1M window → scale 5.0.
    from core.config.authority import set_config_value

    set_config_value("context.window_tokens", "1000000", fresh_db)
    assert context_window_tokens(db_path=fresh_db) == 1_000_000
    assert kb_threshold_scale(db_path=fresh_db) == 5.0
    assert scaled_kb_thresholds(db_path=fresh_db)["handoff"] == HANDOFF_KB * 5

    # Env var wins over ds_config.
    monkeypatch.setenv(ENV, "200000")
    assert context_window_tokens(db_path=fresh_db) == 200_000
    assert kb_threshold_scale(db_path=fresh_db) == 1.0


# ---------------------------------------------------------------------------
# T2 — no premature handoff/compact on the 1M model
# ---------------------------------------------------------------------------


def test_no_premature_handoff_on_1m_model(fresh_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A ~2700 KB transcript trips 'handoff' on the 200k baseline but NOT on the 1M
    model — the size that was ~50% of a 1M window no longer forces a compact/handoff.

    AC: tests/unit/test_context_threshold.py::test_no_premature_handoff_on_1m_model
    """
    from control.context.monitor import kb_to_band

    kb = 2700.0  # the size called out in the WO — ~50% of a 1M window

    # 200k baseline (env unset, fresh db with no config): 2700 KB >= HANDOFF_KB (2500).
    monkeypatch.delenv(ENV, raising=False)
    band_200k, _ = kb_to_band(kb, db_path=fresh_db)
    assert band_200k == "handoff"

    # 1M model: scaled handoff threshold is 12500 KB → 2700 KB is well below it.
    monkeypatch.setenv(ENV, "1000000")
    band_1m, _ = kb_to_band(kb)
    assert band_1m != "handoff"
    assert band_1m != "compact"
    assert band_1m != "urgent"
    assert band_1m == "ok"


# ---------------------------------------------------------------------------
# T3 — end-to-end: scaling resolves the false-pressure bug
# ---------------------------------------------------------------------------


def test_end_to_end(fresh_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: on the 1M model the bands only escalate near the real window, while
    the 200k baseline still escalates at the original KB sizes.

    AC: tests/unit/test_context_threshold.py::test_end_to_end
    """
    from control.context.handoff import HANDOFF_KB, scaled_kb_thresholds
    from control.context.monitor import kb_to_band

    # On the 1M model, the handoff threshold scales to 5x, and a transcript that only
    # reaches the *old* handoff size stays 'ok'; one that reaches the scaled size trips.
    monkeypatch.setenv(ENV, "1000000")
    scaled_handoff = scaled_kb_thresholds()["handoff"]
    assert scaled_handoff == HANDOFF_KB * 5
    assert kb_to_band(float(HANDOFF_KB))[0] == "ok"
    assert kb_to_band(scaled_handoff)[0] == "handoff"

    # On the 200k baseline the original behavior is preserved.
    monkeypatch.delenv(ENV, raising=False)
    assert kb_to_band(float(HANDOFF_KB), db_path=fresh_db)[0] == "handoff"
