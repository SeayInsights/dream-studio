from __future__ import annotations
import re
import pytest


def test_valid_envelope_construction():
    from canonical.events.envelope import CanonicalEventEnvelope
    env = CanonicalEventEnvelope(
        event_type="prompt.lifecycle.submitted",
        session_id="sess-123",
        payload={"prompt_hash": "abc", "raw_retained": False},
    )
    d = env.to_dict()
    assert d["event_type"] == "prompt.lifecycle.submitted"
    assert d["session_id"] == "sess-123"
    assert d["raw_prompt_retained"] is False
    assert d["raw_tool_output_retained"] is False


def test_required_fields_present():
    from canonical.events.envelope import CanonicalEventEnvelope, REQUIRED_FIELDS
    env = CanonicalEventEnvelope(
        event_type="token.consumption.recorded",
        session_id=None,
        payload={},
    )
    d = env.to_dict()
    for f in REQUIRED_FIELDS:
        assert f in d, f"Missing required field: {f}"


def test_uuid_generation():
    from canonical.events.envelope import CanonicalEventEnvelope
    import re
    env1 = CanonicalEventEnvelope(event_type="x", session_id=None, payload={})
    env2 = CanonicalEventEnvelope(event_type="x", session_id=None, payload={})
    assert env1.event_id != env2.event_id
    uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    assert uuid_pattern.match(env1.event_id)


def test_timestamp_iso_format():
    from canonical.events.envelope import CanonicalEventEnvelope
    env = CanonicalEventEnvelope(event_type="x", session_id=None, payload={})
    assert "T" in env.timestamp
    assert env.timestamp.endswith("+00:00")


def test_validate_envelope_catches_missing_fields():
    from canonical.events.envelope import validate_envelope
    errors = validate_envelope({"event_type": "x"})
    field_errors = [e for e in errors if "missing" in e]
    assert len(field_errors) >= 2


def test_validate_envelope_rejects_raw_prompt_retained():
    from canonical.events.envelope import validate_envelope
    errors = validate_envelope({
        "event_id": "x",
        "event_type": "x",
        "timestamp": "2026-05-15T00:00:00+00:00",
        "schema_version": 1,
        "raw_prompt_retained": True,
    })
    assert any("raw_prompt_retained" in e for e in errors)
