from __future__ import annotations
import pytest


def test_all_hook_types_defined():
    from canonical.events.types import EventType, EventCategory, EVENT_TYPE_REGISTRY

    hook_types = [m for m in EVENT_TYPE_REGISTRY if m.category == EventCategory.HOOK_EMITTED]
    # 14 original + TOKEN_CONSUMED (added TA3) = 15
    assert len(hook_types) == 15


def test_production_types_defined():
    from canonical.events.types import EventType, EventCategory, EVENT_TYPE_REGISTRY

    prod_types = [m for m in EVENT_TYPE_REGISTRY if m.category == EventCategory.PRODUCTION_EMITTED]
    assert len(prod_types) >= 28


def test_emitter_implemented_count():
    from canonical.events.types import EMITTER_IMPLEMENTED

    # Hook-emitted implemented types (backward-compat set)
    # 5 original + TOKEN_CONSUMED (TA3) = 6
    assert len(EMITTER_IMPLEMENTED) == 6


def test_exercised_types_flagged():
    from canonical.events.types import EMITTER_IMPLEMENTED, EventType

    expected = {
        EventType.SESSION_LIFECYCLE_STARTED,
        EventType.PROMPT_LIFECYCLE_SUBMITTED,
        EventType.TOOL_EXECUTION_COMPLETED,
        EventType.TOKEN_CONSUMPTION_RECORDED,
        EventType.CONTEXT_THRESHOLD_CROSSED,
        EventType.TOKEN_CONSUMED,  # added TA3
    }
    assert expected == EMITTER_IMPLEMENTED


def test_hook_reserved_types_not_implemented():
    from canonical.events.types import (
        EMITTER_IMPLEMENTED,
        EventType,
        EventCategory,
        EVENT_TYPE_REGISTRY,
    )

    hook_not_implemented = {
        m.event_type
        for m in EVENT_TYPE_REGISTRY
        if m.category == EventCategory.HOOK_EMITTED and not m.emitter_implemented
    }
    assert len(hook_not_implemented) == 9
    assert EventType.SESSION_LIFECYCLE_ENDED in hook_not_implemented
    assert EventType.INTEGRATION_HEALTH_CHANGED in hook_not_implemented


def test_registry_covers_all_types():
    from canonical.events.types import EVENT_TYPE_REGISTRY, EventType

    registry_types = {m.event_type for m in EVENT_TYPE_REGISTRY}
    assert registry_types == set(EventType)


def test_registry_hook_emitter_implemented_consistent():
    """Hook-emitted types: emitter_implemented must match EMITTER_IMPLEMENTED set."""
    from canonical.events.types import EMITTER_IMPLEMENTED, EVENT_TYPE_REGISTRY, EventCategory

    for meta in EVENT_TYPE_REGISTRY:
        if meta.category == EventCategory.HOOK_EMITTED:
            expected = meta.event_type in EMITTER_IMPLEMENTED
            assert meta.emitter_implemented == expected, (
                f"{meta.event_type}: emitter_implemented={meta.emitter_implemented}, "
                f"expected {expected}"
            )


def test_event_category_enum():
    from canonical.events.types import EventCategory

    assert EventCategory.HOOK_EMITTED == "hook_emitted"
    assert EventCategory.PRODUCTION_EMITTED == "production_emitted"
    assert EventCategory.RESERVED == "reserved"


def test_production_event_types_have_correct_values():
    from canonical.events.types import EventType

    assert EventType.GUARDRAIL_DECISION == "guardrail.decision"
    assert EventType.WAVE_STARTED == "wave.started"
    assert EventType.DOCUMENT_CREATED == "document.created"
    assert EventType.ANALYSIS_STARTED == "analysis.started"


def test_work_order_started_in_registry():
    from canonical.events.types import EventType, EVENT_TYPE_REGISTRY

    registry_types = {m.event_type for m in EVENT_TYPE_REGISTRY}
    assert EventType.WORK_ORDER_STARTED in registry_types


def test_work_order_closed_in_registry():
    from canonical.events.types import EventType, EVENT_TYPE_REGISTRY

    registry_types = {m.event_type for m in EVENT_TYPE_REGISTRY}
    assert EventType.WORK_ORDER_CLOSED in registry_types


def test_gate_bypassed_in_registry():
    from canonical.events.types import EventType, EVENT_TYPE_REGISTRY

    registry_types = {m.event_type for m in EVENT_TYPE_REGISTRY}
    assert EventType.GATE_BYPASSED in registry_types


def test_task_completed_in_registry():
    from canonical.events.types import EventType, EVENT_TYPE_REGISTRY

    registry_types = {m.event_type for m in EVENT_TYPE_REGISTRY}
    assert EventType.TASK_COMPLETED in registry_types


def test_milestone_completed_in_registry():
    from canonical.events.types import EventType, EVENT_TYPE_REGISTRY

    registry_types = {m.event_type for m in EVENT_TYPE_REGISTRY}
    assert EventType.MILESTONE_COMPLETED in registry_types
