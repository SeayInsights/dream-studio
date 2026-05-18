from __future__ import annotations
import pytest


def test_emitter_output_to_spool_writer_creates_file(spool_root):
    from emitters.claude_code.emitter import normalize_user_prompt_submit
    from emitters.shared.spool_writer import write_envelopes
    from spool.states import SpoolState, state_dir

    envelopes = normalize_user_prompt_submit({"prompt": "test"}, root=spool_root)
    write_envelopes(envelopes, root=spool_root)

    spool_dir = state_dir(SpoolState.SPOOL, spool_root)
    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)

    # After write_envelopes, inline ingestor runs — file should be in processed/
    # (or spool/ if ingestor was skipped due to DB error, which is fine)
    total_files = list(spool_dir.glob("*.json")) + list(processed_dir.glob("*.json"))
    assert len(total_files) >= 1


def test_empty_envelope_list_is_no_op(spool_root):
    from emitters.shared.spool_writer import write_envelopes
    from spool.states import SpoolState, state_dir

    write_envelopes([], root=spool_root)
    spool_dir = state_dir(SpoolState.SPOOL, spool_root)
    assert list(spool_dir.glob("*.json")) == []
