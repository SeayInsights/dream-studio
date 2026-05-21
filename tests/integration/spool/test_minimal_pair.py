import json


def test_one(spool_root):
    from emitters.claude_code.emitter import normalize_user_prompt_submit
    from emitters.shared.spool_writer import write_envelopes
    from spool.ingestor import ingest, _cleanup_stale_sessions
    from spool.states import SpoolState, state_dir

    hook_payload = {"prompt": "Build a REST API endpoint"}
    envelopes = normalize_user_prompt_submit(hook_payload, root=spool_root)
    write_envelopes(envelopes, root=spool_root)

    ingest(root=spool_root)
    _cleanup_stale_sessions(spool_root)  # Add this explicitly


def test_two(spool_root):
    assert spool_root.exists()
