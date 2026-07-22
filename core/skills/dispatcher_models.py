"""SkillDispatcher result/finding dataclasses — build, audit, and launch shapes.

Split out of dispatcher.py (WO-GF-CORE-HEALTH-SKILLS): consumed by
dispatcher_class.py.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


class BuildTimeoutError(RuntimeError):
    """Raised when static pass exceeds BUILD_TIMEOUT_SECONDS."""


@dataclass
class BuildFinding:
    """A single finding from build-mode skill dispatch."""

    rule_id: str
    skill_id: str  # e.g., "code-quality:build" — distinguishable from audit findings
    severity: str
    tier: str
    excerpt: str
    explanation: str
    line: int = 0
    finding_hash: str = ""

    def __post_init__(self) -> None:
        if not self.finding_hash:
            raw = f"{self.rule_id}:{self.skill_id}:{self.line}:{self.excerpt[:40]}"
            self.finding_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class BuildResult:
    """Result of a .build() dispatch call."""

    language: str
    verdict: str = "PENDING"  # "CLEAN" | "LAUNCH_BLOCKED" | "LAUNCH_WARNING" | "ADVISORY_ONLY"
    skills_run: list[str] = field(default_factory=list)
    t1_blocking: list[BuildFinding] = field(default_factory=list)
    t2_warnings: list[BuildFinding] = field(default_factory=list)
    t3_advisories: list[BuildFinding] = field(default_factory=list)
    elapsed_ms: float = 0.0
    timed_out: bool = False

    @property
    def all_findings(self) -> list[BuildFinding]:
        return self.t1_blocking + self.t2_warnings + self.t3_advisories

    def to_inline_text(self) -> str:
        """Format findings for inline display with generated code."""
        if self.verdict == "CLEAN":
            return ""

        lines: list[str] = []
        if self.t1_blocking:
            lines.append("")
            for f in self.t1_blocking:
                lines.append(f"\U0001f534 BLOCKED [{f.rule_id}] {f.explanation}")
                if f.excerpt:
                    lines.append(f"   Found: {f.excerpt[:80]}")
        if self.t2_warnings:
            lines.append("")
            for f in self.t2_warnings:
                lines.append(f"\U0001f7e0 WARNING [{f.rule_id}] {f.explanation}")
                if f.excerpt:
                    lines.append(f"   Found: {f.excerpt[:80]}")
        if self.t3_advisories:
            lines.append("")
            for f in self.t3_advisories:
                lines.append(f"ℹ️  ADVISORY [{f.rule_id}] {f.explanation}")
        return "\n".join(lines)


# ── Audit-mode dataclasses ────────────────────────────────────────────────


@dataclass
class AuditFinding:
    """A single finding from full-audit skill dispatch."""

    rule_id: str
    skill_id: str  # plain skill name (e.g., "security") — no :audit suffix per pre-flight
    severity: str
    tier: str
    file_path: str
    line: int = 0
    excerpt: str = ""
    explanation: str = ""
    finding_hash: str = ""

    def __post_init__(self) -> None:
        if not self.finding_hash:
            raw = f"{self.rule_id}:{self.skill_id}:{self.file_path}:{self.line}:{self.excerpt[:40]}"
            self.finding_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class SkillAuditStats:
    """Per-skill audit statistics."""

    skill_id: str
    verdict: str = "PASS"  # PASS / WARNING / FAIL / ERROR / SKIPPED
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    llm_pending_count: int = 0
    estimated_tokens: int = 0
    elapsed_ms: float = 0.0
    error: str | None = None

    @property
    def total_findings(self) -> int:
        return self.critical_count + self.high_count + self.medium_count + self.low_count


@dataclass
class AuditResult:
    """Result of a .audit() dispatch call."""

    scope_path: str
    verdict: str = "PASS"  # "PASS" | "WARNING" | "FAIL" | "AUDIT_ERROR"
    findings: list[AuditFinding] = field(default_factory=list)
    skills_run: list[str] = field(default_factory=list)
    skills_failed: list[str] = field(default_factory=list)
    per_skill: dict[str, SkillAuditStats] = field(default_factory=dict)
    total_tokens_estimated: int = 0
    elapsed_seconds: float = 0.0

    @property
    def critical_findings(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == "critical"]

    @property
    def high_findings(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == "high"]

    def summary_text(self) -> str:
        """Human-readable summary for CLI output."""
        lines = [f"\nDream Studio Full Audit — {self.scope_path}"]
        lines.append("=" * 60)
        for skill_id, stats in self.per_skill.items():
            icon = "✓" if stats.verdict == "PASS" else ("✗" if stats.verdict == "FAIL" else "⚠")
            counts = (
                f"{stats.critical_count}C / {stats.high_count}H / "
                f"{stats.medium_count}M / {stats.low_count}L"
            )
            token_info = (
                f" (est. {stats.estimated_tokens:,} tokens for {stats.llm_pending_count} LLM rules)"
                if stats.llm_pending_count
                else ""
            )
            lines.append(f"  {icon} {skill_id:<20} {stats.verdict:<8}  {counts}{token_info}")
        lines.append("-" * 60)
        lines.append(
            f"Verdict: {self.verdict}  |  "
            f"{len(self.findings)} findings  |  "
            f"{self.total_tokens_estimated:,} tokens estimated  |  "
            f"{self.elapsed_seconds:.1f}s"
        )
        return "\n".join(lines)


# ── LaunchResult dataclass ────────────────────────────────────────────────


@dataclass
class LaunchResult:
    """Result of a .launch() dispatch call."""

    verdict: str  # "LAUNCH_READY" | "LAUNCH_WARNING" | "LAUNCH_BLOCKED"
    service_type: str
    audit_result: AuditResult
    blocking_findings: list[AuditFinding] = field(default_factory=list)
    warning_findings: list[AuditFinding] = field(default_factory=list)
    launch_summary: str = ""
    elapsed_seconds: float = 0.0
    tokens_consumed: int = 0

    @property
    def is_ready(self) -> bool:
        return self.verdict == "LAUNCH_READY"

    @property
    def is_blocked(self) -> bool:
        return self.verdict == "LAUNCH_BLOCKED"


def _meets_threshold(severity: str, threshold: str) -> bool:
    """Return True if severity meets or exceeds threshold."""
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    return order.get(severity, 0) >= order.get(threshold, 0)


def _increment_stat(stats: SkillAuditStats, severity: str) -> None:
    if severity == "critical":
        stats.critical_count += 1
    elif severity == "high":
        stats.high_count += 1
    elif severity == "medium":
        stats.medium_count += 1
    else:
        stats.low_count += 1
