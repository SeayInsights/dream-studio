"""B.4 — `gate.pre_push.failed` event emission tests.

These tests verify the A0 invariant: the pre-push gate runner constructs its
failure event via `CanonicalEventEnvelope` (the dataclass), NOT a hand-built
dict. Hand-built dicts caused the original spool ingest failure that A0
(PR #16) fixed; regressing that pattern is not acceptable.

Coverage:
  * emit_gate_failure_event builds a CanonicalEventEnvelope (not a dict)
  * envelope event_type matches EventType.GATE_PRE_PUSH_FAILED
  * envelope schema_version is set (the A0 guarantee)
  * envelope payload contains the gate id, exit code, hints
  * run_pre_push_gates emits one event per failed gate
  * run_pre_push_gates does not emit events for passing gates
  * spool write failure does NOT abort the pre-push run
  * emit_events=False suppresses emission entirely
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from canonical.events.envelope import CanonicalEventEnvelope
from canonical.events.types import EventType
from core.gates.pre_push import (
    GateResult,
    emit_gate_failure_event,
    run_pre_push_gates,
)


def _write_manifest(path: Path, gates: list[dict]) -> None:
    import yaml as _yaml

    payload = {
        "name": "test-manifest",
        "description": "synthetic",
        "version": 1,
        "gates": gates,
    }
    path.write_text(_yaml.safe_dump(payload), encoding="utf-8")


# ── emit_gate_failure_event ───────────────────────────────────────────────────


def test_emit_uses_canonical_envelope_dataclass():
    """Spool write must receive a CanonicalEventEnvelope instance — not a dict."""
    result = GateResult(
        gate_id="format-check",
        passed=False,
        exit_code=1,
        duration_seconds=0.42,
        fail_hint="run black",
        stderr_tail="would reformat foo.py",
    )
    with patch("emitters.shared.spool_writer.write_envelopes") as mock_write:
        emit_gate_failure_event(result)
    assert mock_write.call_count == 1
    args, _ = mock_write.call_args
    envelopes = args[0]
    assert len(envelopes) == 1
    assert isinstance(envelopes[0], CanonicalEventEnvelope), (
        "B.4 regression: gate.pre_push.failed was emitted as a non-envelope "
        "(violates A0 invariant — must use CanonicalEventEnvelope)."
    )


def test_emit_event_type_matches_registry():
    result = GateResult(gate_id="lint-check", passed=False, exit_code=1, duration_seconds=0.1)
    with patch("emitters.shared.spool_writer.write_envelopes") as mock_write:
        emit_gate_failure_event(result)
    envelope = mock_write.call_args[0][0][0]
    assert envelope.event_type == EventType.GATE_PRE_PUSH_FAILED.value
    assert envelope.event_type == "gate.pre_push.failed"


def test_emit_envelope_has_schema_version():
    """A0 invariant: schema_version is set on every envelope (dataclass guarantees this)."""
    result = GateResult(gate_id="test-suite", passed=False, exit_code=1, duration_seconds=1.5)
    with patch("emitters.shared.spool_writer.write_envelopes") as mock_write:
        emit_gate_failure_event(result)
    envelope = mock_write.call_args[0][0][0]
    assert envelope.schema_version == 1
    # The to_dict serialization must also preserve schema_version.
    assert envelope.to_dict()["schema_version"] == 1


def test_emit_payload_carries_gate_diagnostics():
    result = GateResult(
        gate_id="skill-sync",
        passed=False,
        exit_code=42,
        duration_seconds=2.71,
        fail_hint="enforcement-block regressed",
        stderr_tail="cli_refs: [py -m interfaces.cli.ds]",
        stdout_tail="some stdout",
    )
    with patch("emitters.shared.spool_writer.write_envelopes") as mock_write:
        emit_gate_failure_event(result)
    envelope = mock_write.call_args[0][0][0]
    assert envelope.payload["gate_id"] == "skill-sync"
    assert envelope.payload["exit_code"] == 42
    assert envelope.payload["duration_seconds"] == 2.71
    assert envelope.payload["fail_hint"] == "enforcement-block regressed"
    assert "py -m interfaces.cli.ds" in envelope.payload["stderr_tail"]


def test_emit_swallows_spool_write_failure(capsys):
    """A spool write failure must NOT propagate — pre-push hook integrity comes first."""
    result = GateResult(gate_id="docs-drift", passed=False, exit_code=1, duration_seconds=0.5)
    with patch(
        "emitters.shared.spool_writer.write_envelopes",
        side_effect=OSError("disk full"),
    ):
        emit_gate_failure_event(result)  # must not raise
    err = capsys.readouterr().err
    assert "spool write failed" in err
    assert "docs-drift" in err


# ── run_pre_push_gates ────────────────────────────────────────────────────────


def test_run_pre_push_gates_emits_one_event_per_failed_gate(tmp_path: Path):
    manifest = tmp_path / "m.yaml"
    _write_manifest(
        manifest,
        [
            {"id": "g1-fail", "command": [sys.executable, "-c", "import sys; sys.exit(1)"]},
            {"id": "g2-fail", "command": [sys.executable, "-c", "import sys; sys.exit(1)"]},
        ],
    )
    with patch("emitters.shared.spool_writer.write_envelopes") as mock_write:
        run_pre_push_gates(
            manifest_path=manifest,
            repo_root=tmp_path,
            stop_on_first_failure=False,
            emit_events=True,
        )
    assert mock_write.call_count == 2
    emitted_gate_ids = [call.args[0][0].payload["gate_id"] for call in mock_write.call_args_list]
    assert sorted(emitted_gate_ids) == ["g1-fail", "g2-fail"]


def test_run_pre_push_gates_does_not_emit_for_passing_gates(tmp_path: Path):
    manifest = tmp_path / "m.yaml"
    _write_manifest(
        manifest,
        [
            {"id": "g1-pass", "command": [sys.executable, "-c", "pass"]},
            {"id": "g2-pass", "command": [sys.executable, "-c", "pass"]},
        ],
    )
    with patch("emitters.shared.spool_writer.write_envelopes") as mock_write:
        run_pre_push_gates(
            manifest_path=manifest,
            repo_root=tmp_path,
            emit_events=True,
        )
    assert mock_write.call_count == 0


def test_emit_events_false_suppresses_emission(tmp_path: Path):
    manifest = tmp_path / "m.yaml"
    _write_manifest(
        manifest,
        [{"id": "g1-fail", "command": [sys.executable, "-c", "import sys; sys.exit(1)"]}],
    )
    with patch("emitters.shared.spool_writer.write_envelopes") as mock_write:
        run_pre_push_gates(
            manifest_path=manifest,
            repo_root=tmp_path,
            emit_events=False,
        )
    assert mock_write.call_count == 0
