from __future__ import annotations

from .event_type_registry_shared import RegistryEntry, _BUSINESS

_BUSINESS_ENTRIES: tuple[RegistryEntry, ...] = (
    # ── Business-only: Pure SDLC operator actions ─────────────────────────────
    # These represent changes TO the project/SDLC state, driven by operator
    # commands. No AI execution is the primary cause.
    RegistryEntry(
        "project.created", _BUSINESS, "meaningful-unit", "Project registered in Dream Studio"
    ),
    RegistryEntry(
        "project.deleted",
        _BUSINESS,
        "meaningful-unit",
        "Project deleted with cascade to milestones, work orders, tasks",
    ),
    RegistryEntry(
        "project.activated",
        _BUSINESS,
        "meaningful-unit",
        "Project set as the active project (status → active)",
        payload_required_keys=frozenset({"project_id"}),
    ),
    RegistryEntry(
        "project.deactivated",
        _BUSINESS,
        "meaningful-unit",
        "Project deactivated (status → paused)",
        payload_required_keys=frozenset({"project_id"}),
    ),
    RegistryEntry(
        "project.registered",
        _BUSINESS,
        "meaningful-unit",
        "Project registered in the analysis registry",
    ),
    RegistryEntry(
        "project.updated", _BUSINESS, "meaningful-unit", "Project metadata updated in registry"
    ),
    RegistryEntry(
        "milestone.created", _BUSINESS, "meaningful-unit", "New milestone created under a project"
    ),
    RegistryEntry("milestone.deleted", _BUSINESS, "meaningful-unit", "Milestone deleted"),
    RegistryEntry(
        "milestone.completed",
        _BUSINESS,
        "meaningful-unit",
        "Milestone closed after gate verification",
    ),
    RegistryEntry(
        "work_order.created",
        _BUSINESS,
        "meaningful-unit",
        "New work order created under a milestone or project",
        payload_required_keys=frozenset({"title", "status", "type"}),
    ),
    RegistryEntry(
        "work_order.started",
        _BUSINESS,
        "meaningful-unit",
        "Work order entered in_progress state",
        payload_required_keys=frozenset({"work_order_id", "title", "type", "project_id"}),
    ),
    RegistryEntry(
        "work_order.blocked",
        _BUSINESS,
        "meaningful-unit",
        "Work order blocked with a stated reason",
        payload_required_keys=frozenset({"work_order_id", "title", "project_id", "reason"}),
    ),
    RegistryEntry(
        "work_order.unblocked",
        _BUSINESS,
        "meaningful-unit",
        "Work order unblocked and returned to in_progress state",
        payload_required_keys=frozenset({"work_order_id", "title", "project_id"}),
    ),
    RegistryEntry(
        "work_order.closed",
        _BUSINESS,
        "meaningful-unit",
        "Work order closed after gate checks passed",
        payload_required_keys=frozenset({"work_order_id", "title", "project_id", "forced"}),
    ),
    RegistryEntry(
        "work_order.deleted",
        _BUSINESS,
        "meaningful-unit",
        "Work order deleted via cascade from project deletion",
        payload_required_keys=frozenset({"work_order_id", "project_id"}),
    ),
    # Ordering/dependency mutations (core/work_orders/ordering.py). Emitted for
    # audit via AD-6 emit-then-SQL; not consumed by any projection, so no
    # payload_required_keys enforcement. Registered so the ingestor does not
    # warn "event_type ... not in registry" on set_sequence_order/add_dependency.
    RegistryEntry(
        "work_order.reordered",
        _BUSINESS,
        "meaningful-unit",
        "Work order sequence_order changed (sparse 10/20/30 convention)",
    ),
    RegistryEntry(
        "work_order.dependency_added",
        _BUSINESS,
        "meaningful-unit",
        "Dependency edge added: work order waits for another to close",
    ),
    RegistryEntry(
        "work_order.dependency_removed",
        _BUSINESS,
        "meaningful-unit",
        "Dependency edge removed between two work orders",
    ),
    RegistryEntry(
        "design_brief.created",
        _BUSINESS,
        "meaningful-unit",
        "Draft design brief created for a project",
        payload_required_keys=frozenset({"brief_id", "project_id"}),
    ),
    RegistryEntry(
        "design_brief.updated",
        _BUSINESS,
        "meaningful-unit",
        "One field updated on a draft design brief",
        payload_required_keys=frozenset({"brief_id", "field", "new_value"}),
    ),
    RegistryEntry(
        "design_brief.locked",
        _BUSINESS,
        "meaningful-unit",
        "Design brief locked (human approval gate passed)",
        payload_required_keys=frozenset({"brief_id"}),
    ),
    RegistryEntry(
        "design_brief.deleted",
        _BUSINESS,
        "meaningful-unit",
        "Design brief deleted via cascade from project deletion",
        payload_required_keys=frozenset({"brief_id", "project_id"}),
    ),
    RegistryEntry("task.created", _BUSINESS, "meaningful-unit", "New task added to a work order"),
    RegistryEntry("task.started", _BUSINESS, "meaningful-unit", "Work began on a task"),
    RegistryEntry(
        "task.deleted",
        _BUSINESS,
        "meaningful-unit",
        "Task deleted via cascade from project or work order deletion",
    ),
    RegistryEntry(
        "task.completed", _BUSINESS, "meaningful-unit", "Task marked complete within a work order"
    ),
    RegistryEntry(
        "preflight.created",
        _BUSINESS,
        "meaningful-unit",
        "New preflight finding recorded on a work order (blast_radius/impact/risk/spec_reference/dependency)",
    ),
    RegistryEntry(
        "preflight.status_changed",
        _BUSINESS,
        "meaningful-unit",
        "Preflight finding status updated (open/acknowledged/mitigated/accepted_risk/resolved)",
    ),
    RegistryEntry(
        "gate.bypassed",
        _BUSINESS,
        "meaningful-unit",
        "Gate check bypassed with --force (operator decision, auditable)",
    ),
    RegistryEntry(
        "gate.pre_push.failed",
        _BUSINESS,
        "meaningful-unit",
        "Pre-push gate failed during ds workflow run pre-push",
    ),
    RegistryEntry(
        "document.created", _BUSINESS, "meaningful-unit", "Document created in document store"
    ),
    RegistryEntry(
        "document.updated", _BUSINESS, "meaningful-unit", "Document updated in document store"
    ),
    RegistryEntry(
        "document.archived", _BUSINESS, "meaningful-unit", "Document archived in document store"
    ),
    RegistryEntry(
        "system.task_status.updated",
        _BUSINESS,
        "meaningful-unit",
        "PRD task status updated (blocked, in_progress, completed)",
    ),
)
