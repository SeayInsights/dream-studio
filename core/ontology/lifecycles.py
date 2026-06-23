"""Domain-scoped lifecycle enums and catalog declarations.

Each domain defines its own lifecycle enum with values matching its persisted
convention. The LIFECYCLE_CATALOG is built once from frozen declarations.

Lifecycle enums are plain Enum (not str, Enum) to prevent accidental
cross-domain or raw-string equality. All string conversion goes through
explicit boundary helpers: from_db_value(), to_db_value().

Persistence conventions (do NOT normalize globally):
  - Memory: uppercase   ("DRAFT", "ACTIVE", "ARCHIVED")
  - Execution: lowercase ("pending", "active", "completed")
  - Document: lowercase  ("active", "archived")
"""

from enum import Enum
from typing import Optional

from core.ontology.registry import LifecycleSpec, TypeCatalog

# ── Memory lifecycle ────────────────────────────────────────────────────────


class MemoryLifecycle(Enum):
    DRAFT = "DRAFT"
    CANDIDATE = "CANDIDATE"
    PROMOTED = "PROMOTED"
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"

    @classmethod
    def _missing_(cls, value: object) -> Optional["MemoryLifecycle"]:
        if isinstance(value, str):
            upper = value.upper()
            for member in cls:
                if member.value == upper:
                    return member
        return None


MEMORY_TRANSITIONS = {
    "DRAFT": frozenset({"CANDIDATE", "ARCHIVED"}),
    "CANDIDATE": frozenset({"PROMOTED", "ARCHIVED"}),
    "PROMOTED": frozenset({"ACTIVE"}),
    "ACTIVE": frozenset({"STALE", "SUPERSEDED"}),
    "STALE": frozenset({"ACTIVE", "ARCHIVED"}),
    "SUPERSEDED": frozenset({"ARCHIVED"}),
    "ARCHIVED": frozenset(),
}


# ── Execution lifecycle ─────────────────────────────────────────────────────


class ExecutionLifecycle(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

    @classmethod
    def _missing_(cls, value: object) -> Optional["ExecutionLifecycle"]:
        if isinstance(value, str):
            lower = value.lower()
            for member in cls:
                if member.value == lower:
                    return member
        return None


EXECUTION_TRANSITIONS = {
    "pending": frozenset({"active", "blocked", "skipped"}),
    "active": frozenset({"completed", "failed", "blocked"}),
    "blocked": frozenset({"pending", "active", "skipped"}),
    "completed": frozenset(),
    "failed": frozenset({"pending"}),
    "skipped": frozenset(),
}


# ── Document lifecycle ──────────────────────────────────────────────────────


class DocumentLifecycle(Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"

    @classmethod
    def _missing_(cls, value: object) -> Optional["DocumentLifecycle"]:
        if isinstance(value, str):
            lower = value.lower()
            for member in cls:
                if member.value == lower:
                    return member
        return None


DOCUMENT_TRANSITIONS = {
    "active": frozenset({"archived"}),
    "archived": frozenset({"active"}),
}


# ── Parse/normalize helpers ─────────────────────────────────────────────────


def from_db_value(value: str, lifecycle_cls: type[Enum]) -> Enum | None:
    """Parse a persisted string into its lifecycle enum member.

    Case-insensitive via _missing_ hook on each lifecycle enum.
    Returns None if the value is not a valid member.
    """
    if not value:
        return None
    try:
        return lifecycle_cls(value)
    except ValueError:
        return None


def to_db_value(state: Enum) -> str:
    """Return the canonical persisted string for a lifecycle state."""
    return state.value


def normalize_lifecycle(value: str, lifecycle_cls: type[Enum]) -> Enum | None:
    """Alias for from_db_value — normalize a raw string to a lifecycle enum."""
    return from_db_value(value, lifecycle_cls)


# ── Catalog construction ────────────────────────────────────────────────────

LIFECYCLE_CATALOG = TypeCatalog(
    specs=[
        LifecycleSpec(
            entity_type="memory",
            lifecycle_enum=MemoryLifecycle,
            transitions=MEMORY_TRANSITIONS,
        ),
        LifecycleSpec(
            entity_type="workflow",
            lifecycle_enum=ExecutionLifecycle,
            transitions=EXECUTION_TRANSITIONS,
        ),
        LifecycleSpec(
            entity_type="workflow_node",
            lifecycle_enum=ExecutionLifecycle,
            transitions=EXECUTION_TRANSITIONS,
        ),
        LifecycleSpec(
            entity_type="session",
            lifecycle_enum=ExecutionLifecycle,
            transitions=EXECUTION_TRANSITIONS,
        ),
        LifecycleSpec(
            entity_type="finding",
            lifecycle_enum=ExecutionLifecycle,
            transitions=EXECUTION_TRANSITIONS,
        ),
        LifecycleSpec(
            entity_type="artifact",
            lifecycle_enum=DocumentLifecycle,
            transitions=DOCUMENT_TRANSITIONS,
        ),
        # EVENT, TRACE — lifecycle-less (immutable entities, not registered)
        # AGENT, POLICY — unmanaged (lifecycle not yet defined, not registered)
    ]
)
