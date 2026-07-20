from __future__ import annotations
import json
import pytest


def test_hook_json_to_spool_to_processed(spool_root):
    """Simulate: hook JSON → emitter → spool write → explicit ingest → file in processed/."""
    from emitters.claude_code.emitter import normalize_user_prompt_submit
    from emitters.shared.spool_writer import write_envelopes
    from spool.ingestor import ingest_pending
    from spool.states import SpoolState, state_dir

    hook_payload = {"prompt": "Build a REST API endpoint"}
    envelopes = normalize_user_prompt_submit(hook_payload, root=spool_root)
    assert len(envelopes) == 1

    write_envelopes(envelopes, root=spool_root)

    # After spool write, events are in spool/ (not yet ingested)
    spool_dir = state_dir(SpoolState.SPOOL, spool_root)
    assert len(list(spool_dir.glob("*.json"))) == 1

    # After explicit ingest, file moves to processed/
    ingest_pending(root=spool_root)
    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)
    processed_files = list(processed_dir.glob("*.json"))
    assert len(processed_files) == 1

    data = json.loads(processed_files[0].read_text(encoding="utf-8"))
    assert data["event_type"] == "prompt.lifecycle.submitted"
    assert data["raw_prompt_retained"] is False
