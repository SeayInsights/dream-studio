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

# Canonical skill rules.yml paths
_SKILL_MODES_ROOT = Path(__file__).parents[3] / "canonical" / "skills" / "quality" / "modes"

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
