"""SkillDispatcher — build-mode orchestration for generated code quality enforcement.

Phase 1 (18.8.1): implements .build() only.
Phase 2 (18.8.2): adds .audit() for full-project audit.
Pre-launch Phase 2: adds .launch() for release-gate verdict.

Shared infrastructure at class level (thresholds, findings glue, logging) is
usable by future sibling modes. Build .build() first, add siblings without
redesign.

Performance contract: .build() static pass must complete in < 2 seconds.
Hard stop enforced — raises BuildTimeoutError on exceed.

Usage:
    result = SkillDispatcher.build(
        code_artifact=generated_code,
        language="python",
        context={"project_id": "...", "session_id": "..."},
    )
    if result.verdict == "LAUNCH_BLOCKED":
        # surface T1 findings to user

WO-GF-CORE-HEALTH-SKILLS: implementation moved to dispatcher_{shared,models,
class}.py; this module re-exports the public+private surface so existing
`from core.skills.dispatcher import X` callers are unchanged.
"""

from __future__ import annotations

from .dispatcher_class import SkillDispatcher
from .dispatcher_models import (
    AuditFinding,
    AuditResult,
    BuildFinding,
    BuildResult,
    BuildTimeoutError,
    LaunchResult,
    SkillAuditStats,
    _increment_stat,
    _meets_threshold,
)
from .dispatcher_shared import (
    BUILD_TIMEOUT_SECONDS,
    TIER_T1,
    TIER_T2,
    TIER_T3,
    _LANGUAGE_SKILL_MAP,
    _SEVERITY_TO_TIER,
    logger,
)

__all__ = [
    "AuditFinding",
    "AuditResult",
    "BUILD_TIMEOUT_SECONDS",
    "BuildFinding",
    "BuildResult",
    "BuildTimeoutError",
    "LaunchResult",
    "SkillAuditStats",
    "SkillDispatcher",
    "TIER_T1",
    "TIER_T2",
    "TIER_T3",
    "_LANGUAGE_SKILL_MAP",
    "_SEVERITY_TO_TIER",
    "_increment_stat",
    "_meets_threshold",
    "logger",
]
