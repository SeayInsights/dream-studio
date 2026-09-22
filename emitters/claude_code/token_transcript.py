"""WO-TOKEN-CAPTURE-REAL: real per-turn token capture from the session transcript.

Claude Code's PostToolUse payload carries no per-tool token counts, so the live emitter
never captured real usage — the dashboard's token total (~364k) was retired-rollup noise
plus dev-branch test fixtures, not reality (true usage is millions). The only authoritative
source is the session transcript: each assistant turn records a `message.usage` block
(input/output + cache tokens) and its model.

At Stop, this parses the transcript and emits one `token.consumed` per assistant turn with
exactly the payload keys the DuckDB `token_usage_records` view sums (input_tokens,
output_tokens, cache_creation_input_tokens, cache_read_input_tokens, model). The event_id is
derived from the transcript entry uuid, so re-emitting across repeated Stop invocations is
idempotent (the ingestor does INSERT OR IGNORE on the event_id PK; events_fact dedups on
event_id) — no separate dedup state is needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from canonical.events.envelope import CanonicalEventEnvelope
from canonical.events.types import EventType
from emitters.claude_code.session import get_or_create_session_id


def _iter_usage_entries(text: str) -> Iterator[tuple[str, dict, str, bool]]:
    """Yield (entry_uuid, usage, model, is_sidechain) for lines carrying token usage.

    ``isSidechain`` is on every usage-bearing entry and marks a SUBAGENT turn. Reading it
    is the difference between "this session cost 9.2M tokens" and "the main thread cost X
    and the specialists cost Y" -- the second is a question about how the platform
    dispatches work, and it was unanswerable while the flag sat unread in the file.

    WHAT IS DELIBERATELY NOT TAKEN FROM HERE. Which agent a sidechain turn belongs to is
    not on the entry; recovering it means walking `parentUuid` back to the dispatching
    Task call. `slug` looks like a candidate and is not -- it is a session nickname, one
    distinct value across 4,347 entries. Stamping it as an agent id would be a fabricated
    dimension that reads as measured, which is worse than the gap.
    """
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        msg = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        usage = entry.get("usage")
        if not isinstance(usage, dict):
            usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else None
        if not usage:
            continue
        uid = entry.get("uuid") or msg.get("id")
        if not uid:
            continue
        model = entry.get("model") or msg.get("model") or ""
        yield str(uid), usage, str(model), bool(entry.get("isSidechain"))


def _resolve_project_id(payload: dict[str, Any]) -> str | None:
    """The project the work actually happened in — not the globally-active one.

    This used to call get_active_project_id(), which answers a different
    question: "which project did the operator last mark active?" A session doing
    Fulcrum work while Dream Studio was the active project had every one of its
    token events attributed to Dream Studio. That is not a missing label, it is a
    wrong one, and it silently moves spend between clients.

    Resolution order, evidence-first:
      1. the .dream-studio-project marker at the process cwd — the same resolver
         core/telemetry/token_capture.py already uses, and the work's own location
      2. the cwd carried on the hook payload, for the case where the emitter runs
         somewhere other than the session's directory
      3. NULL

    There is deliberately no fall-back to the active project. Coverage bought
    with a guess is worse than an honest gap: an unattributed event is visibly
    unattributed, whereas a mis-attributed one inflates a client's spend and
    nothing downstream can tell.
    """
    try:
        from core.sdlc.cwd_resolver import resolve_project_from_cwd

        ctx = resolve_project_from_cwd()
        if ctx is not None and ctx.project_id:
            return str(ctx.project_id)
    except Exception:
        pass

    raw_cwd = payload.get("cwd")
    if raw_cwd:
        try:
            from core.sdlc.cwd_resolver import resolve_project_from_path

            ctx = resolve_project_from_path(Path(str(raw_cwd)))
            if ctx is not None and ctx.project_id:
                return str(ctx.project_id)
        except Exception:
            pass

    return None


def _resolve_work_order_id(project_id: str | None) -> str | None:
    """The in-progress work order this session's spend belongs to, or None.

    WHY THIS IS HERE AT ALL. `work_order_id`, `task_id` and `agent_id` all read **0%**
    across 86,241 token.consumed rows -- recorded in `core/analytics/duckdb_store.py`,
    which notes they were 0 "not because nothing resolved them, but because nothing
    carried them across", and that "what did this work order cost" was unanswerable for
    that reason alone. The reader was taught to pick these out of `trace`; nothing ever
    put them there. This is the writing half.

    Resolved ONCE per emission, not per turn: a Stop hook pays for this, and a transcript
    carries thousands of usage entries. The query is read-only and indexed.

    A WORK ORDER, NOT A TASK. A turn does not belong to one task -- a single assistant
    turn routinely advances several, and picking one would be a guess presented as a
    measurement. The work order is the smallest unit this evidence actually supports, and
    tasks roll up to it.

    Best-effort, like everything else on this path: an unreadable authority costs a
    dimension, never an event.
    """
    if not project_id:
        return None
    try:
        from runtime.lib.enforcement import in_progress_work_order

        row = in_progress_work_order(project_id)
    except Exception:
        return None
    if not isinstance(row, dict):
        return None
    wo = row.get("work_order_id")
    return str(wo) if wo else None


def _resolve_task_id(work_order_id: str | None) -> str | None:
    """The single in-progress task, or None when the answer is not single.

    THIS BECAME ANSWERABLE, it was not before. Tasks went `created -> complete` with no
    state between, so at every instant there was no current task and a turn could not be
    charged to one. `start_task` adds the middle state and this reads it.

    ONE, OR NOTHING. Several tasks may be in progress at once -- the model routinely
    advances more than one in a turn, and `start_task` returns `siblings_in_progress` for
    exactly that reason. Picking the newest would produce a task id that looks measured
    and is a guess; two tasks in progress means the honest answer to "which task did this
    turn cost" is "the work order, and no further".

    THE READ LIVES IN runtime.lib.enforcement, not here. `emitters/` is pure
    normalization and may not open a database -- the sibling resolver above already asks
    that layer for its answer, and this one briefly did not.

    Best-effort: an unreadable authority costs a dimension, never an event.
    """
    if not work_order_id:
        return None
    try:
        from runtime.lib.enforcement import in_progress_task_ids

        task_ids = in_progress_task_ids(work_order_id)
    except Exception:
        return None
    return task_ids[0] if len(task_ids) == 1 else None


def normalize_stop_token_usage(
    payload: dict[str, Any], root: Path | None = None
) -> list[CanonicalEventEnvelope]:
    """Return one token.consumed envelope per assistant turn in the session transcript."""
    transcript_path = payload.get("transcript_path") or ""
    if not transcript_path:
        return []
    path = Path(transcript_path)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    session_id = get_or_create_session_id(root)
    project_id = _resolve_project_id(payload)
    work_order_id = _resolve_work_order_id(project_id)
    task_id = _resolve_task_id(work_order_id)

    envelopes: list[CanonicalEventEnvelope] = []
    for uid, usage, model, is_sidechain in _iter_usage_entries(text):

        def _int(key: str) -> int:
            try:
                return int(usage.get(key) or 0)
            except (TypeError, ValueError):
                return 0

        inp = _int("input_tokens")
        out = _int("output_tokens")
        cache_write = _int("cache_creation_input_tokens")
        cache_read = _int("cache_read_input_tokens")
        if inp == 0 and out == 0 and cache_write == 0 and cache_read == 0:
            continue  # no real usage on this turn
        envelopes.append(
            CanonicalEventEnvelope(
                event_id=f"tok-{uid}",
                event_type=EventType.TOKEN_CONSUMED.value,
                session_id=session_id,
                payload={
                    "input_tokens": inp,
                    "output_tokens": out,
                    "cache_creation_input_tokens": cache_write,
                    "cache_read_input_tokens": cache_read,
                    "model": model,
                    "granularity": "assistant_turn",
                },
                project_id=project_id,
                # project_id also goes in the trace so it survives any reader
                # that only looks there; the ingestor accepts it from either.
                trace={
                    "domain": "telemetry",
                    "model_id": model,
                    "project_id": project_id,
                    # THE DIMENSIONS THAT READ 0%. `ai_canonical_events` has no
                    # work_order_id column, so the reader takes it from here --
                    # see the COALESCE in core/analytics/duckdb_store.py.
                    "work_order_id": work_order_id,
                    # Present only when exactly one task claims to be running. None is
                    # an honest "the work order, and no further", not a missing value.
                    "task_id": task_id,
                    # A subagent turn, so spend splits between the main thread and
                    # the specialists. Not WHICH specialist: that is not on the
                    # entry, and inventing it would be a fabricated dimension.
                    "is_sidechain": is_sidechain,
                    "attribution_status": "cwd" if project_id else "orphan",
                },
            )
        )
    return envelopes
