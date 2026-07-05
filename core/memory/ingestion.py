"""Memory ingestion pipeline — feeds source systems into memory_entries.

Each IngestionConsumer reads from a source table/system and writes to
memory_entries via MemoryStore.upsert_by_provenance() for idempotency.

This is NOT an event-sourcing projection — it's a batch sync from domain
tables (raw_lessons, reg_gotchas, etc.) that don't flow through canonical_events.
"""

import logging
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any
from uuid import uuid4

from core.config.database import get_connection
from core.memory.store import MemoryEntry, MemoryStore, _auto_tags, _infer_category
from core.ontology.lifecycles import MemoryLifecycle, to_db_value

logger = logging.getLogger(__name__)


@dataclass
class IngestionRecord:
    """Contract: every ingestion source must produce these fields."""

    source_type: str
    source_id: str
    memory_type: str
    content: str
    confidence: float | None
    category: str
    tags: list[str]
    metadata: dict[str, Any]
    original_timestamp: str
    project: str | None = None
    skill: str | None = None


@dataclass
class IngestionResult:
    consumer_name: str
    records_found: int
    records_ingested: int
    records_updated: int
    records_skipped: int
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


class IngestionConsumer(ABC):
    """Base class for memory ingestion consumers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def source_type(self) -> str: ...

    @abstractmethod
    def fetch_pending(self, conn: sqlite3.Connection) -> list[IngestionRecord]:
        """Fetch records from the source that need ingestion."""
        ...

    def ingest(self, store: MemoryStore) -> IngestionResult:
        """Run ingestion: fetch pending records and upsert into memory_entries."""
        start = time.monotonic()
        result = IngestionResult(
            consumer_name=self.name,
            records_found=0,
            records_ingested=0,
            records_updated=0,
            records_skipped=0,
        )

        with get_connection(read_only=True) as conn:
            records = self.fetch_pending(conn)

        result.records_found = len(records)

        for record in records:
            try:
                self._ingest_one(record, store, result)
            except Exception as e:
                result.errors.append(f"{record.source_id}: {e}")
                logger.warning(f"Ingestion error for {record.source_id}: {e}")

        result.duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            f"[{self.name}] ingested={result.records_ingested} "
            f"updated={result.records_updated} errors={len(result.errors)} "
            f"in {result.duration_ms:.0f}ms"
        )
        return result

    def _ingest_one(
        self, record: IngestionRecord, store: MemoryStore, result: IngestionResult
    ) -> None:
        now = datetime.now(UTC).isoformat()

        existing = self._find_existing(record, store)

        entry = MemoryEntry(
            memory_id=existing.memory_id if existing else str(uuid4()),
            memory_type=record.memory_type,
            category=record.category,
            content=record.content[:2000],
            source_type=record.source_type,
            source_id=record.source_id,
            lifecycle_state=(
                existing.lifecycle_state if existing else to_db_value(MemoryLifecycle.DRAFT)
            ),
            metadata=record.metadata,
            importance=existing.importance if existing else self._initial_importance(record),
            confidence=record.confidence,
            tags=record.tags,
            project=record.project,
            skill=record.skill,
            provenance={
                "source_type": record.source_type,
                "source_id": record.source_id,
                "ingested_at": now,
                "ingested_by": self.name,
                "original_timestamp": record.original_timestamp,
            },
        )

        store.upsert_by_provenance(entry)

        if existing:
            result.records_updated += 1
        else:
            result.records_ingested += 1

    def _find_existing(self, record: IngestionRecord, store: MemoryStore) -> MemoryEntry | None:
        with get_connection(read_only=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM memory_entries WHERE source_type = ? AND source_id = ?",
                (record.source_type, record.source_id),
            ).fetchone()
            if row:
                return store._row_to_entry(row)
        return None

    def _initial_importance(self, record: IngestionRecord) -> float:
        if record.confidence is not None:
            return 0.4 + (record.confidence * 0.4)
        return 0.5


class LessonIngestionConsumer(IngestionConsumer):
    """Ingests raw_lessons into memory_entries."""

    @property
    def name(self) -> str:
        return "lesson_ingestion"

    @property
    def source_type(self) -> str:
        return "raw_lessons"

    def fetch_pending(self, conn: sqlite3.Connection) -> list[IngestionRecord]:
        rows = conn.execute("""
            SELECT rl.lesson_id, rl.source, rl.confidence, rl.status,
                   rl.title, rl.what_happened, rl.lesson, rl.evidence,
                   rl.created_at
            FROM raw_lessons rl
            WHERE rl.lesson_id NOT IN (
                SELECT source_id FROM memory_entries
                WHERE source_type = 'raw_lessons' AND source_id IS NOT NULL
            )
        """).fetchall()

        records = []
        for row in rows:
            lesson_id = row[0]
            source = row[1]
            confidence_str = row[2]
            status = row[3]
            title = row[4]
            what_happened = row[5] or ""
            lesson_text = row[6] or ""
            evidence = row[7] or ""
            created_at = row[8]

            confidence = {"high": 0.9, "medium": 0.6, "low": 0.3}.get(
                (confidence_str or "medium").lower(), 0.5
            )

            content = f"{title}\n\n{lesson_text}"
            if what_happened:
                content += f"\n\nContext: {what_happened}"

            tags = _auto_tags(content)
            tags.append(f"status:{status}")
            if source:
                tags.append(f"origin:{source}")

            records.append(
                IngestionRecord(
                    source_type="raw_lessons",
                    source_id=lesson_id,
                    memory_type="lesson",
                    content=content,
                    confidence=confidence,
                    category=_infer_category(content),
                    tags=tags,
                    metadata={
                        "raw_status": status,
                        "raw_source": source,
                        "evidence": evidence,
                    },
                    original_timestamp=created_at or "",
                )
            )

        return records


class GotchaIngestionConsumer(IngestionConsumer):
    """Ingests reg_gotchas into memory_entries."""

    @property
    def name(self) -> str:
        return "gotcha_ingestion"

    @property
    def source_type(self) -> str:
        return "reg_gotchas"

    def fetch_pending(self, conn: sqlite3.Connection) -> list[IngestionRecord]:
        rows = conn.execute("""
            SELECT rg.gotcha_id, rg.skill_id, rg.severity, rg.title,
                   rg.context, rg.fix, rg.keywords, rg.discovered, rg.times_hit
            FROM reg_gotchas rg
            WHERE rg.gotcha_id NOT IN (
                SELECT source_id FROM memory_entries
                WHERE source_type = 'reg_gotchas' AND source_id IS NOT NULL
            )
        """).fetchall()

        records = []
        for row in rows:
            gotcha_id = row[0]
            skill_id = row[1]
            severity = row[2]
            title = row[3]
            context = row[4] or ""
            fix = row[5] or ""
            keywords = row[6] or ""
            discovered = row[7] or ""
            times_hit = row[8] or 0

            content = f"{title}"
            if context:
                content += f"\n\nContext: {context}"
            if fix:
                content += f"\n\nFix: {fix}"

            tags = ["gotcha", severity.lower()]
            if keywords:
                tags.extend(k.strip() for k in keywords.split(",") if k.strip())

            records.append(
                IngestionRecord(
                    source_type="reg_gotchas",
                    source_id=gotcha_id,
                    memory_type="gotcha",
                    content=content,
                    confidence=1.0,
                    category=_infer_category(content),
                    tags=tags,
                    metadata={
                        "severity": severity,
                        "times_hit": times_hit,
                        "keywords": keywords,
                    },
                    original_timestamp=discovered,
                    skill=skill_id,
                )
            )

        return records

    def _initial_importance(self, record: IngestionRecord) -> float:
        severity = record.metadata.get("severity", "medium")
        return {"critical": 0.95, "high": 0.8, "medium": 0.6, "low": 0.4}.get(severity.lower(), 0.5)


# CorrectionIngestionConsumer RETIRED migration 131: cor_skill_corrections table
# (and its dead writer skill_correct()) were dropped, so there is no source to
# ingest. The consumer + its registration in run_all_ingestion() are removed.


class DecisionIngestionConsumer(IngestionConsumer):
    """Ingests decision events from canonical_events into memory_entries.

    Reads decision.* and guardrail.decision events directly from the event store.
    """

    @property
    def name(self) -> str:
        return "decision_ingestion"

    @property
    def source_type(self) -> str:
        return "canonical_events"

    def fetch_pending(self, conn: sqlite3.Connection) -> list[IngestionRecord]:
        try:
            rows = conn.execute("""
                SELECT event_id, event_type, timestamp, payload, severity,
                       confidence_score, source_type
                FROM canonical_events
                WHERE (event_type LIKE 'decision.%' OR event_type = 'guardrail.decision')
                  AND event_id NOT IN (
                      SELECT source_id FROM memory_entries
                      WHERE source_type = 'canonical_events' AND source_id IS NOT NULL
                  )
                ORDER BY timestamp ASC
            """).fetchall()
        except Exception:
            return []

        import json as _json

        records = []
        for row in rows:
            event_id = row[0]
            event_type = row[1]
            timestamp = row[2]
            payload_raw = row[3]
            severity = row[4]
            confidence = row[5]
            evt_source = row[6]

            try:
                payload = _json.loads(payload_raw) if payload_raw else {}
            except (TypeError, ValueError):
                payload = {}

            decision_type = payload.get("decision_type", event_type)
            outcome = payload.get("outcome", payload.get("action", ""))
            reasoning = payload.get("reasoning", "")
            if isinstance(reasoning, dict):
                reasoning = reasoning.get("rationale", str(reasoning))
            subsystem = payload.get("subsystem", evt_source or "unknown")

            content = f"Decision [{decision_type}]: {outcome}"
            if reasoning:
                content += f"\nReasoning: {reasoning}"

            records.append(
                IngestionRecord(
                    source_type="canonical_events",
                    source_id=event_id,
                    memory_type="decision",
                    content=content,
                    confidence=confidence or payload.get("confidence", 0.7),
                    category=decision_type,
                    tags=["decision", subsystem, severity or "info"],
                    metadata={
                        "event_type": event_type,
                        "outcome": outcome,
                        "subsystem": subsystem,
                        "payload": payload,
                    },
                    original_timestamp=timestamp or "",
                )
            )

        return records


def run_all_ingestion(store: MemoryStore | None = None) -> list[IngestionResult]:
    """Run all ingestion consumers and return results."""
    if store is None:
        store = MemoryStore()

    consumers: list[IngestionConsumer] = [
        LessonIngestionConsumer(),
        GotchaIngestionConsumer(),
        # CorrectionIngestionConsumer retired migration 131 (cor_skill_corrections dropped)
        DecisionIngestionConsumer(),
    ]

    results = []
    for consumer in consumers:
        try:
            results.append(consumer.ingest(store))
        except Exception as e:
            logger.error(f"Ingestion consumer {consumer.name} failed: {e}")
            results.append(
                IngestionResult(
                    consumer_name=consumer.name,
                    records_found=0,
                    records_ingested=0,
                    records_updated=0,
                    records_skipped=0,
                    errors=[str(e)],
                )
            )

    return results
