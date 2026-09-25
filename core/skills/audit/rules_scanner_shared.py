"""Rules-scanner shared constants and result dataclasses.

Split out of rules_scanner.py (WO-GF-CORE-HEALTH-SKILLS): data leaf consumed
by rules_scanner_checks.py and rules_scanner_core.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("core.skills.audit.rules_scanner")

# Canonical skills root -- a skill_id's owning pack is resolved per lookup
# (_skill_dir below), not hardcoded, because the pack-split campaign keeps
# moving these skill_ids between packs (ops/pre-launch: quality -> release;
# architecture/testing/types-deps are quality today and will move too).
_SKILLS_ROOT = Path(__file__).parents[3] / "canonical" / "skills"


def _skill_dir(skill_id: str) -> Path:
    """The mode directory for *skill_id*, wherever its pack currently is.

    Searches canonical/skills/*/modes/<skill_id> rather than assuming a
    fixed pack, so a pack-split move doesn't silently stop this scanner
    from finding the skill's rules.yml/config.yml (found the hard way:
    ops/pre-launch moved to release and this returned no match until
    fixed). Falls back to the pre-split quality/modes/<skill_id> location
    if no pack owns it (keeps existing behavior/error messages for a
    typo'd or genuinely-missing skill_id).
    """
    matches = sorted(_SKILLS_ROOT.glob(f"*/modes/{skill_id}"))
    if matches:
        return matches[0]
    return _SKILLS_ROOT / "quality" / "modes" / skill_id


# File patterns per language tag
_LANG_PATTERNS: dict[str, tuple[str, ...]] = {
    "python": ("*.py",),
    "typescript": ("*.ts", "*.tsx"),
    "javascript": ("*.js", "*.jsx"),
    "go": ("*.go",),
    "rust": ("*.rs",),
    "sql": ("*.sql",),
}

_SKIP_DIRS = frozenset(
    {".venv", "venv", "node_modules", ".git", "__pycache__", ".planning", "dist", "build"}
)

# Average tokens per character for LLM prompt estimation (~4 chars per token)
_CHARS_PER_TOKEN = 4
# Base prompt overhead per LLM rule call (system prompt + rule template)
_BASE_PROMPT_TOKENS = 500


@dataclass
class LLMPendingItem:
    """A rule that requires LLM evaluation (not run in this static pass)."""

    rule_id: str
    skill_id: str
    severity: str
    file_path: str
    estimated_tokens: int
    explanation: str = "LLM semantic evaluation pending"


@dataclass
class SkillScanResult:
    """Result of running a single skill's static scanner on a scope."""

    skill_id: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    llm_pending: list[LLMPendingItem] = field(default_factory=list)
    files_scanned: int = 0
    files_skipped: int = 0
    error: str | None = None

    @property
    def total_estimated_tokens(self) -> int:
        return sum(p.estimated_tokens for p in self.llm_pending)
