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
from emitters.claude_code.project import _get_db_path, get_active_project_id
from emitters.claude_code.session import get_or_create_session_id


def _iter_usage_entries(text: str) -> Iterator[tuple[str, dict, str]]:
    """Yield (entry_uuid, usage, model) for transcript lines carrying token usage."""
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
        yield str(uid), usage, str(model)


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
    try:
        project_id = get_active_project_id(_get_db_path())
    except Exception:
        project_id = None

    envelopes: list[CanonicalEventEnvelope] = []
    for uid, usage, model in _iter_usage_entries(text):

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
                trace={"domain": "telemetry", "model_id": model},
            )
        )
    return envelopes
