"""Canonical event type registry for dream-studio.

This module defines all valid business event types that can be emitted via EventStore.
Use constants instead of raw strings to prevent typos and enable IDE autocomplete.

Created: 2026-05-07 (Phase 1 Wave 1 - EventStore Migration)
"""


class EventType:
    """Canonical event type constants."""

    # Analysis events
    ANALYSIS_STARTED = "analysis.started"
    ANALYSIS_COMPLETED = "analysis.completed"
    REPO_ANALYZED = "repo.analyzed"
    FINDING_CREATED = "finding.created"
    FINDING_RESOLVED = "finding.resolved"

    # Workflow events
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_LEARNED = "workflow.learned"

    # Research events
    RESEARCH_STARTED = "research.started"
    RESEARCH_COMPLETED = "research.completed"
    MEMORY_STORED = "memory.stored"
    MEMORY_RETRIEVED = "memory.retrieved"

    # Model events
    MODEL_SELECTED = "model.selected"
    MODEL_INVOKED = "model.invoked"
    MODEL_RESPONSE_RECEIVED = "model.response.received"

    # Session events
    SESSION_STARTED = "session.started"
    SESSION_RESUMED = "session.resumed"
    SESSION_COMPACTED = "session.compacted"
    SESSION_ENDED = "session.ended"

    # Tool events
    TOOL_INVOKED = "tool.invoked"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"

    # Hook events
    HOOK_TRIGGERED = "hook.triggered"
    HOOK_COMPLETED = "hook.completed"
    HOOK_FAILED = "hook.failed"

    # Skill events
    SKILL_LOADED = "skill.loaded"
    SKILL_INVOKED = "skill.invoked"
    SKILL_COMPLETED = "skill.completed"

    # Admin events (CLI tools)
    BACKFILL_STARTED = "backfill.started"
    BACKFILL_COMPLETED = "backfill.completed"
    MIGRATION_APPLIED = "migration.applied"
    DATABASE_MERGED = "database.merged"

    # Alert events
    ALERT_CREATED = "alert.created"
    ALERT_ACKNOWLEDGED = "alert.acknowledged"
    ALERT_RESOLVED = "alert.resolved"

    # Security events
    SCAN_STARTED = "scan.started"
    SCAN_COMPLETED = "scan.completed"
    VULNERABILITY_FOUND = "vulnerability.found"
    VULNERABILITY_MITIGATED = "vulnerability.mitigated"

    # Execution events (added 2026-05-07 - Phase 3 unification)
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETE = "execution.complete"
    EXECUTION_FAILED = "execution.failed"
    TESTS_EXECUTED = "execution.tests_executed"
    CI_STATUS_COLLECTED = "execution.ci_status_collected"

    # Repository extraction events (Wave 1: repo_analyzer.py)
    REPO_EXTRACTION_STORED = "repo.extraction.stored"
    REPO_PATTERN_EXTRACTED = "repo.pattern.extracted"
    REPO_BUILDING_BLOCK_EXTRACTED = "repo.building_block.extracted"

    # Project events (Wave 1.5: analysis/engine.py)
    PROJECT_REGISTERED = "project.registered"
    PROJECT_UPDATED = "project.updated"

    # Analysis lifecycle events (Wave 1.5: analysis/engine.py)
    ANALYSIS_DISCOVERY_COMPLETED = "analysis.discovery_completed"
    ANALYSIS_RESEARCH_COMPLETED = "analysis.research_completed"
    ANALYSIS_AUDIT_COMPLETED = "analysis.audit_completed"
    ANALYSIS_BUG_ANALYSIS_COMPLETED = "analysis.bug_analysis_completed"
    ANALYSIS_SYNTHESIS_COMPLETED = "analysis.synthesis_completed"
    ANALYSIS_FAILED = "analysis.failed"

    # Audit events (Wave 1.5: analysis/audit.py)
    AUDIT_VIOLATIONS_CLEARED = "audit.violations_cleared"
    AUDIT_VIOLATION_FOUND = "audit.violation_found"
    AUDIT_IMPROVEMENTS_CLEARED = "audit.improvements_cleared"
    AUDIT_IMPROVEMENT_FOUND = "audit.improvement_found"

    # Wave events (Wave 1.5: execution/workflow/wave_executor.py)
    WAVE_STARTED = "wave.started"
    WAVE_COMPLETED = "wave.completed"
    WAVE_FAILED = "wave.failed"
    WAVE_TASK_UPDATED = "wave.task_updated"

    # Research validation events (Wave 1.5: session/manager.py)
    RESEARCH_VALIDATED = "research.validated"

    # Research cache events (Wave 1.5: research/web.py)
    RESEARCH_CACHE_STORED = "research.cache_stored"
    RESEARCH_CACHE_CLEARED = "research.cache_cleared"

    # Tool cache events (Wave 1.5: research/tools.py)
    TOOL_EMBEDDINGS_CACHE_CLEARED = "tool.embeddings_cache_cleared"

    # Guardrail events
    GUARDRAIL_DECISION = "guardrail.decision"

    # Document events (Wave 2: storage/document_store.py)
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_ARCHIVED = "document.archived"
