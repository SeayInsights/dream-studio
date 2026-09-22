# ---------------------------------------------------------------------------
# The work's identity rides on the token row (B7)
# ---------------------------------------------------------------------------


def _transcript(tmp_path):
    import json as _json

    path = tmp_path / "s.jsonl"
    path.write_text(
        "\n".join(
            _json.dumps(e)
            for e in (
                {
                    "uuid": "u1",
                    "isSidechain": False,
                    "model": "claude-opus-5",
                    "message": {"usage": {"input_tokens": 100, "output_tokens": 50}},
                },
                {
                    "uuid": "u2",
                    "isSidechain": True,
                    "model": "claude-haiku-4-5",
                    "message": {"usage": {"input_tokens": 20, "output_tokens": 10}},
                },
            )
        ),
        encoding="utf-8",
    )
    return path


def test_a_token_row_names_the_work_order_it_belongs_to(tmp_path):
    """MEASURED BEFORE THIS: 0% of 86,241 token.consumed rows carried a work order.

    `core/analytics/duckdb_store.py` records why — the reader was taught to take
    `work_order_id` out of `trace` because the table has no such column, and nothing ever
    put it there. "What did this work order cost" was unanswerable for that reason alone.
    """
    from unittest import mock

    from emitters.claude_code import token_transcript as tt

    with (
        mock.patch.object(tt, "_resolve_project_id", return_value="proj-abc"),
        mock.patch.object(tt, "_resolve_work_order_id", return_value="wo-123"),
    ):
        envelopes = tt.normalize_stop_token_usage({"transcript_path": str(_transcript(tmp_path))})

    assert envelopes, "no token events produced"
    assert all(e.trace.get("work_order_id") == "wo-123" for e in envelopes)


def test_a_subagent_turn_is_distinguishable_from_the_main_thread(tmp_path):
    """`isSidechain` sits on every usage-bearing entry and was never read. It is the
    difference between "this session cost X" and "the main thread cost X and the
    specialists cost Y"."""
    from unittest import mock

    from emitters.claude_code import token_transcript as tt

    with (
        mock.patch.object(tt, "_resolve_project_id", return_value="p"),
        mock.patch.object(tt, "_resolve_work_order_id", return_value="w"),
    ):
        envelopes = tt.normalize_stop_token_usage({"transcript_path": str(_transcript(tmp_path))})

    assert {e.trace["is_sidechain"] for e in envelopes} == {True, False}


def test_no_agent_id_is_invented(tmp_path):
    """WHICH agent a sidechain turn belongs to is not on the transcript entry, and `slug`
    — the obvious candidate — is a session nickname with one distinct value across 4,347
    entries. A fabricated dimension reads as measured, which is worse than the gap."""
    from unittest import mock

    from emitters.claude_code import token_transcript as tt

    with (
        mock.patch.object(tt, "_resolve_project_id", return_value="p"),
        mock.patch.object(tt, "_resolve_work_order_id", return_value="w"),
    ):
        envelopes = tt.normalize_stop_token_usage({"transcript_path": str(_transcript(tmp_path))})

    for e in envelopes:
        assert "agent_id" not in e.trace
        assert "slug" not in e.trace


def test_an_unreadable_authority_costs_a_dimension_not_an_event(tmp_path):
    """Best-effort, like everything on this path. A token event with no work order is
    still a token event; losing the spend record to gain a label would be the wrong
    trade."""
    from unittest import mock

    from emitters.claude_code import token_transcript as tt

    # Patched at the REAL boundary -- the authority read -- not at
    # `_resolve_work_order_id`, whose own try/except is the guard under test. Mocking the
    # guarded function would have tested the mock.
    import runtime.lib.enforcement as enforcement

    with (
        mock.patch.object(tt, "_resolve_project_id", return_value="p"),
        mock.patch.object(
            enforcement, "in_progress_work_order", side_effect=RuntimeError("authority unreadable")
        ),
    ):
        envelopes = tt.normalize_stop_token_usage({"transcript_path": str(_transcript(tmp_path))})

    assert envelopes, "a broken authority took the token events with it"
    assert all(e.trace.get("work_order_id") is None for e in envelopes)
    assert all(e.payload["input_tokens"] for e in envelopes), "the spend itself survived"


def test_a_token_row_names_a_task_only_when_one_claims_to_be_running(tmp_path):
    """`task_id` read 0% because there was nothing to read: tasks went created ->
    complete with no state between, so at every instant no task claimed to be running.
    `start_task` adds the middle state.

    ONE, OR NOTHING. Several tasks can be in progress at once — the model advances more
    than one in a turn, which is why `start_task` returns `siblings_in_progress`. Picking
    the newest would yield an id that looks measured and is a guess.
    """
    from unittest import mock

    from emitters.claude_code import token_transcript as tt

    for expected in ("task-abc", None):
        with (
            mock.patch.object(tt, "_resolve_project_id", return_value="p"),
            mock.patch.object(tt, "_resolve_work_order_id", return_value="wo-1"),
            mock.patch.object(tt, "_resolve_task_id", return_value=expected),
        ):
            envelopes = tt.normalize_stop_token_usage(
                {"transcript_path": str(_transcript(tmp_path))}
            )
        assert all(e.trace["task_id"] == expected for e in envelopes)
        assert all(
            e.trace["work_order_id"] == "wo-1" for e in envelopes
        ), "the work order must survive an unresolvable task"
