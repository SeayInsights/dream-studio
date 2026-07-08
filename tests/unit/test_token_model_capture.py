"""Regression tests for WO-TOKEN-MODEL-CAPTURE.

The dashboard cost was frozen because the dominant token event family
(token.consumption.recorded, emitted by normalize_stop from the per-session
accumulator) carried no model, so the DuckDB token_usage_records view priced
it to NULL. Root cause: token_capture._update_session_accumulator persisted
only the four token-count keys and dropped the model that handle_post_tool_use
had already resolved, and normalize_stop never re-attached one.

These tests pin the fix: the accumulator persists the model, and normalize_stop
stamps a model onto the emitted event (from the accumulator, else recovered
from the Stop payload's transcript_path). Model is recovered truth, never
fabricated — a modelless turn still emits no model.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


def test_accumulator_persists_model(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    from core.telemetry.token_capture import _update_session_accumulator

    session_id = "model-acc-001"
    _update_session_accumulator(session_id, {"input_tokens": 100, "model": "claude-opus-4-8"})
    # A later modelless turn must not wipe the captured model.
    _update_session_accumulator(session_id, {"input_tokens": 50})

    acc = json.loads(
        (tmp_path / ".dream-studio" / "state" / f"session-tokens-{session_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert acc["input_tokens"] == 150
    assert acc["model"] == "claude-opus-4-8"


def test_stop_event_carries_model(tmp_path, monkeypatch):
    """normalize_stop stamps the accumulator's model onto the emitted event."""
    session_id = "model-stop-001"
    acc_dir = tmp_path / ".dream-studio" / "state"
    acc_dir.mkdir(parents=True, exist_ok=True)
    (acc_dir / f"session-tokens-{session_id}.json").write_text(
        json.dumps({"input_tokens": 300, "output_tokens": 120, "model": "claude-opus-4-8"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with patch("emitters.claude_code.emitter.get_or_create_session_id", return_value=session_id):
        from emitters.claude_code.emitter import normalize_stop

        envelopes = normalize_stop({})

    assert len(envelopes) == 1
    assert envelopes[0].payload["model"] == "claude-opus-4-8"
    assert envelopes[0].payload["input_tokens"] == 300


def test_stop_event_recovers_model_from_transcript(tmp_path, monkeypatch):
    """When the accumulator has no model, normalize_stop recovers it from the
    Stop payload's transcript_path (the same resolver token_capture uses)."""
    session_id = "model-stop-002"
    acc_dir = tmp_path / ".dream-studio" / "state"
    acc_dir.mkdir(parents=True, exist_ok=True)
    # Accumulator without a model (pre-fix data / usage-only turns).
    (acc_dir / f"session-tokens-{session_id}.json").write_text(
        json.dumps({"input_tokens": 10, "output_tokens": 5}), encoding="utf-8"
    )
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "assistant", "message": {"model": "claude-sonnet-4-6"}}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with patch("emitters.claude_code.emitter.get_or_create_session_id", return_value=session_id):
        from emitters.claude_code.emitter import normalize_stop

        envelopes = normalize_stop({"transcript_path": str(transcript)})

    assert envelopes[0].payload["model"] == "claude-sonnet-4-6"


def test_stop_event_has_no_model_when_none_available(tmp_path, monkeypatch):
    """A modelless turn with no transcript emits no model — never fabricated."""
    session_id = "model-stop-003"
    acc_dir = tmp_path / ".dream-studio" / "state"
    acc_dir.mkdir(parents=True, exist_ok=True)
    (acc_dir / f"session-tokens-{session_id}.json").write_text(
        json.dumps({"input_tokens": 10, "output_tokens": 5}), encoding="utf-8"
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with patch("emitters.claude_code.emitter.get_or_create_session_id", return_value=session_id):
        from emitters.claude_code.emitter import normalize_stop

        envelopes = normalize_stop({})

    assert "model" not in envelopes[0].payload
