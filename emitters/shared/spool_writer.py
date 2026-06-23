from __future__ import annotations
from pathlib import Path
from collections.abc import Sequence

from canonical.events.envelope import CanonicalEventEnvelope
from spool.writer import write_event


def write_envelopes(envelopes: Sequence[CanonicalEventEnvelope], root: Path | None = None) -> None:
    """Write envelopes atomically to spool/. Does NOT call the ingestor.

    Ingestion is triggered separately via `ds spool ingest` CLI or the Stop hook.
    The spool write is the durability boundary — raises on file write failure.
    """
    for envelope in envelopes:
        write_event(envelope.to_dict(), root=root)
