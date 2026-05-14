"""Fluent API wrapper for decision querying."""

from __future__ import annotations
from typing import Optional

from . import query_engine
from .schema import Decision


class DecisionQuery:
    """Fluent API for querying decisions."""

    def __init__(self):
        self._decision_type: Optional[str] = None
        self._subsystem: Optional[str] = None
        self._min_confidence: Optional[float] = None
        self._limit: int = 100

    def decisions(self) -> DecisionQuery:
        """Start a decision query (chainable)."""
        return self

    def where(self, decision_type: str) -> DecisionQuery:
        """Filter by decision type."""
        self._decision_type = decision_type
        return self

    def from_subsystem(self, subsystem: str) -> DecisionQuery:
        """Filter by source subsystem."""
        self._subsystem = subsystem
        return self

    def min_confidence(self, confidence: float) -> DecisionQuery:
        """Filter by minimum confidence."""
        self._min_confidence = confidence
        return self

    def limit(self, limit: int) -> DecisionQuery:
        """Set result limit."""
        self._limit = limit
        return self

    def execute(self) -> list[Decision]:
        """Execute the query and return results."""
        return query_engine.get_decisions(
            decision_type=self._decision_type,
            subsystem=self._subsystem,
            min_confidence=self._min_confidence,
            limit=self._limit,
        )

    def explain(self, decision_id: str) -> dict:
        """Explain a decision by ID."""
        return query_engine.explain_decision(decision_id)

    def trace(self, event_id: str) -> dict:
        """Trace event to decisions and caused events."""
        return query_engine.trace_event(event_id)

    def audit(self, decision_type: str) -> dict:
        """Audit decisions of a specific type."""
        return query_engine.audit_decisions(decision_type)


# Singleton instance for convenient imports
query = DecisionQuery()
