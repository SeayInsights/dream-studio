"""SkillDispatcher shared constants — tiers, severity mapping, language map.

Split out of dispatcher.py (WO-GF-CORE-HEALTH-SKILLS): data leaf consumed by
dispatcher_class.py.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("core.skills.dispatcher")

# ── Tier constants ─────────────────────────────────────────────────────────
TIER_T1 = "T1"  # launch blocking — block return
TIER_T2 = "T2"  # launch warning — return with inline warning
TIER_T3 = "T3"  # advisory — return with collapsed note

# ── Severity → Tier mapping per skill at build time ────────────────────────
# Most skills: critical/high → T1, medium → T2, low → T3.
# Exceptions: security/database escalate high → T1 because correctness matters.
_SEVERITY_TO_TIER: dict[str, dict[str, str]] = {
    "security": {"critical": TIER_T1, "high": TIER_T1, "medium": TIER_T2, "low": TIER_T3},
    "database": {"critical": TIER_T1, "high": TIER_T1, "medium": TIER_T2, "low": TIER_T3},
    "code-quality": {"critical": TIER_T1, "high": TIER_T2, "medium": TIER_T3, "low": TIER_T3},
    "default": {"critical": TIER_T1, "high": TIER_T2, "medium": TIER_T3, "low": TIER_T3},
}

# ── Language → skill set mapping ───────────────────────────────────────────
# Based on roadmap: Python → security + code-quality + database; React/TS → security + code-quality
_LANGUAGE_SKILL_MAP: dict[str, list[str]] = {
    "python": ["security", "code-quality", "database"],
    "sql": ["database"],
    "typescript": ["security", "code-quality"],
    "javascript": ["security", "code-quality"],
    "tsx": ["security", "code-quality"],
    "jsx": ["security", "code-quality"],
    "go": [],  # no go build-mode auditors in Phase 1; deferred
    "rust": [],  # no rust build-mode auditors in Phase 1; deferred
}

# Static pass budget in seconds (hard stop)
BUILD_TIMEOUT_SECONDS = 2.0
