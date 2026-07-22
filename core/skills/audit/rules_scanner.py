"""Rules-based scanner for quality skills that don't have Python build auditors.

Parses each skill's rules.yml to extract static detection triggers + file patterns,
runs them against actual files, and records LLM-only rules as "pending" with token
estimates (no external API call required).

Token estimation is accurate enough for the roadmap exit criterion
"token budget measured + validated" without requiring API keys.

WO-GF-CORE-HEALTH-SKILLS: implementation moved to rules_scanner_{shared,checks,
core}.py; this module re-exports the public+private surface so existing
`from core.skills.audit.rules_scanner import X` callers are unchanged.
"""

from __future__ import annotations

from .rules_scanner_checks import (
    _check_architecture,
    _check_ops,
    _check_pre_launch,
    _check_testing,
    _check_types_deps,
    _infer_service_type,
    _is_handled_by_specific_check,
    _run_skill_specific_checks,
)
from .rules_scanner_core import RulesScanner, _extract_code_patterns, _severity_to_tier
from .rules_scanner_shared import (
    _BASE_PROMPT_TOKENS,
    _CHARS_PER_TOKEN,
    _LANG_PATTERNS,
    _SKILL_MODES_ROOT,
    _SKIP_DIRS,
    LLMPendingItem,
    SkillScanResult,
    logger,
)

__all__ = [
    "LLMPendingItem",
    "RulesScanner",
    "SkillScanResult",
    "_BASE_PROMPT_TOKENS",
    "_CHARS_PER_TOKEN",
    "_LANG_PATTERNS",
    "_SKILL_MODES_ROOT",
    "_SKIP_DIRS",
    "_check_architecture",
    "_check_ops",
    "_check_pre_launch",
    "_check_testing",
    "_check_types_deps",
    "_extract_code_patterns",
    "_infer_service_type",
    "_is_handled_by_specific_check",
    "_run_skill_specific_checks",
    "_severity_to_tier",
    "logger",
]
