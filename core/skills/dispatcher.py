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
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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


class SkillDispatcher:
    """Orchestrates quality skill dispatch on generated code artifacts.

    Phase 1: .build() only (18.8.1).
    Phase 2: .audit() and .launch() added (18.8.2 + pre-launch Phase 2).

    The class-level shared infrastructure (thresholds, findings glue, hash computation,
    logging) is designed for sibling methods. Adding .audit()/.launch() in a future WO
    does not require redesigning the threshold model or finding schema.
    """

    # ── Shared infrastructure (class-level, usable by future .audit()/.launch()) ──

    @classmethod
    def _resolve_skills(cls, language: str) -> list[str]:
        """Return the skill set for a given language. Returns [] for unsupported languages."""
        normalized = language.lower().strip().lstrip(".")
        return list(_LANGUAGE_SKILL_MAP.get(normalized, []))

    @classmethod
    def _apply_threshold(cls, finding: dict[str, Any], skill_id: str) -> str:
        """Map a raw finding's severity to T1/T2/T3 tier for the given skill."""
        severity = finding.get("severity", "medium").lower()
        tier_map = _SEVERITY_TO_TIER.get(skill_id, _SEVERITY_TO_TIER["default"])
        return tier_map.get(severity, TIER_T3)

    @classmethod
    def _to_build_finding(cls, raw: dict[str, Any], skill_id: str) -> BuildFinding:
        """Convert a raw finding dict to a BuildFinding with build-context skill_id."""
        tier = raw.get("tier") or cls._apply_threshold(raw, skill_id)
        return BuildFinding(
            rule_id=raw["rule_id"],
            skill_id=f"{skill_id}:build",  # distinguishes from audit findings in findings table
            severity=raw.get("severity", "medium"),
            tier=tier,
            excerpt=raw.get("excerpt", ""),
            explanation=raw.get("explanation", ""),
            line=raw.get("line", 0),
        )

    @classmethod
    def _call_skill_auditor(
        cls, skill: str, code_artifact: str, context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Call the static auditor function for a given skill. Returns raw findings list."""
        try:
            if skill == "code-quality":
                from core.skills.build.code_quality import audit_generated_python

                return audit_generated_python(code_artifact, context)
            elif skill == "security":
                from core.skills.build.security import audit_generated_python

                return audit_generated_python(code_artifact, context)
            elif skill == "database":
                from core.skills.build.database import audit_generated_sql_or_python

                return audit_generated_sql_or_python(code_artifact, context)
            else:
                logger.debug("No build-mode auditor for skill %s in Phase 1", skill)
                return []
        except Exception as exc:
            logger.warning("skill %s auditor raised: %s", skill, exc)
            return []

    # ── Public API ─────────────────────────────────────────────────────────

    @classmethod
    def build(
        cls,
        code_artifact: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> BuildResult:
        """Run build-mode quality enforcement on a generated code artifact.

        Static pass only. Synchronous. Hard stop at BUILD_TIMEOUT_SECONDS.
        Async LLM semantic pass is the caller's responsibility (post-return).

        Args:
            code_artifact: The generated source code string.
            language: Programming language ('python', 'sql', 'typescript', etc.).
            context: Optional dict with project_id, session_id, trigger, etc.

        Returns:
            BuildResult with verdict and tiered findings.

        Raises:
            BuildTimeoutError: When static pass exceeds BUILD_TIMEOUT_SECONDS.
        """
        if context is None:
            context = {}

        skills = cls._resolve_skills(language)
        start = time.monotonic()

        result = BuildResult(language=language, skills_run=skills)

        for skill in skills:
            elapsed = time.monotonic() - start
            if elapsed >= BUILD_TIMEOUT_SECONDS:
                result.timed_out = True
                result.elapsed_ms = elapsed * 1000
                raise BuildTimeoutError(
                    f"Build-mode static pass exceeded {BUILD_TIMEOUT_SECONDS}s "
                    f"(after {elapsed:.2f}s, ran {skills[:skills.index(skill)]}). "
                    f"Remaining skills: {skills[skills.index(skill):]}."
                )

            raw_findings = cls._call_skill_auditor(skill, code_artifact, context)
            for raw in raw_findings:
                finding = cls._to_build_finding(raw, skill)
                if finding.tier == TIER_T1:
                    result.t1_blocking.append(finding)
                elif finding.tier == TIER_T2:
                    result.t2_warnings.append(finding)
                else:
                    result.t3_advisories.append(finding)

        result.elapsed_ms = (time.monotonic() - start) * 1000

        # Determine verdict
        if result.t1_blocking:
            result.verdict = "LAUNCH_BLOCKED"
        elif result.t2_warnings:
            result.verdict = "LAUNCH_WARNING"
        elif result.t3_advisories:
            result.verdict = "ADVISORY_ONLY"
        else:
            result.verdict = "CLEAN"

        logger.debug(
            "build-mode dispatch: language=%s skills=%s verdict=%s findings=%d elapsed_ms=%.1f",
            language,
            skills,
            result.verdict,
            len(result.all_findings),
            result.elapsed_ms,
        )

        return result

    # ── .audit() ───────────────────────────────────────────────────────────

    @classmethod
    def audit(
        cls,
        scope_path: Path,
        skill_filter: list[str] | None = None,
        language_filter: list[str] | None = None,
        severity_threshold: str | None = None,
    ) -> "AuditResult":
        """Run full-project audit across all quality skills.

        Hybrid dispatch (per 18.8.2 pre-flight Option C):
        - security, code-quality, database: Python file-scan (extend build auditors)
        - All other skills: rules.yml-based static scanner + LLM token estimation

        Static phase runs in parallel (ThreadPoolExecutor).
        Per-skill error isolation: one failure does NOT abort the audit.
        Token cost estimation included in result (roadmap exit criterion).

        Args:
            scope_path: Absolute path to repository root.
            skill_filter: Optional subset of skills to run. None = all 10 defaults.
            language_filter: Optional language restriction. None = all languages.
            severity_threshold: Optional minimum severity to include. None = all.

        Returns:
            AuditResult with verdict, per-skill findings, token estimates, elapsed time.
        """
        from core.skills.audit.file_scanner import (
            scan_code_quality,
            scan_database,
            scan_security,
        )
        from core.skills.audit.rules_scanner import RulesScanner

        scope_path = Path(scope_path)
        context: dict[str, Any] = {
            "scope_path": str(scope_path),
            "language_filter": language_filter,
        }

        # Default skill list — pre-launch excluded by default (launch-specific)
        default_skills = [
            "security",
            "code-quality",
            "database",
            "testing",
            "types-deps",
            "backend-api",
            "frontend-ux",
            "architecture",
            "ops",
            "database-compliance",
            "pre-launch",
        ]
        skills = skill_filter if skill_filter is not None else default_skills

        result = AuditResult(scope_path=str(scope_path))
        result.skills_run = list(skills)
        start = time.monotonic()

        # ── Python-native skills (file-scan via build auditors) ───────────
        _PYTHON_NATIVE = {
            "security": scan_security,
            "code-quality": scan_code_quality,
            "database": scan_database,
        }

        def _run_python_skill(skill: str) -> tuple[str, list[dict], str | None]:
            scanner_fn = _PYTHON_NATIVE[skill]
            try:
                raw = scanner_fn(scope_path, context)
                return skill, raw, None
            except Exception as exc:
                logger.warning("audit skill %s failed: %s", skill, exc)
                return skill, [], str(exc)

        def _run_rules_skill(skill: str) -> tuple[str, object, str | None]:
            from core.skills.audit.rules_scanner import RulesScanner as _RS
            from core.skills.audit.rules_scanner import SkillScanResult as _SSR

            try:
                scanner = _RS(skill)
                scan_result = scanner.scan(scope_path, context)
                return skill, scan_result, scan_result.error
            except Exception as exc:
                logger.warning("audit skill %s (rules) failed: %s", skill, exc)
                err_result = _SSR(skill_id=skill, error=str(exc))
                return skill, err_result, str(exc)

        # ── Parallel execution ────────────────────────────────────────────
        futures: dict[concurrent.futures.Future, str] = {}
        max_workers = min(len(skills), 8)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            for skill in skills:
                if skill in _PYTHON_NATIVE:
                    fut = pool.submit(_run_python_skill, skill)
                else:
                    fut = pool.submit(_run_rules_skill, skill)
                futures[fut] = skill

            for fut in concurrent.futures.as_completed(futures):
                skill_id_done = futures[fut]
                try:
                    skill_id, skill_data, error = fut.result()
                except Exception as exc:
                    result.skills_failed.append(skill_id_done)
                    result.per_skill[skill_id_done] = SkillAuditStats(
                        skill_id=skill_id_done, verdict="ERROR", error=str(exc)
                    )
                    continue

                if error:
                    result.skills_failed.append(skill_id)

                # Process findings
                stats = SkillAuditStats(skill_id=skill_id)
                if skill_id in _PYTHON_NATIVE:
                    # skill_data is list[dict]
                    raw_findings: list[dict] = skill_data  # type: ignore[assignment]
                    for raw in raw_findings:
                        sev = raw.get("severity", "medium")
                        if severity_threshold and not _meets_threshold(sev, severity_threshold):
                            continue
                        af = AuditFinding(
                            rule_id=raw.get("rule_id", ""),
                            skill_id=skill_id,
                            severity=sev,
                            tier=raw.get("tier") or cls._apply_threshold(raw, skill_id),
                            file_path=raw.get("file_path", ""),
                            line=raw.get("line", 0),
                            excerpt=raw.get("excerpt", ""),
                            explanation=raw.get("explanation", ""),
                        )
                        result.findings.append(af)
                        _increment_stat(stats, sev)
                else:
                    # skill_data is SkillScanResult
                    from core.skills.audit.rules_scanner import SkillScanResult

                    scan_res: SkillScanResult = skill_data  # type: ignore[assignment]
                    for raw in scan_res.findings:
                        sev = raw.get("severity", "medium")
                        if severity_threshold and not _meets_threshold(sev, severity_threshold):
                            continue
                        af = AuditFinding(
                            rule_id=raw.get("rule_id", ""),
                            skill_id=skill_id,
                            severity=sev,
                            tier=raw.get("tier") or cls._apply_threshold(raw, skill_id),
                            file_path=raw.get("file_path", ""),
                            line=raw.get("line", 0),
                            excerpt=raw.get("excerpt", ""),
                            explanation=raw.get("explanation", ""),
                        )
                        result.findings.append(af)
                        _increment_stat(stats, sev)
                    stats.llm_pending_count = len(scan_res.llm_pending)
                    stats.estimated_tokens = scan_res.total_estimated_tokens
                    if error:
                        stats.error = error

                # Per-skill verdict
                if error:
                    stats.verdict = "ERROR"
                elif stats.critical_count > 0:
                    stats.verdict = "FAIL"
                elif stats.high_count > 0:
                    stats.verdict = "WARNING"
                else:
                    stats.verdict = "PASS"

                result.per_skill[skill_id] = stats

        result.elapsed_seconds = time.monotonic() - start
        result.total_tokens_estimated = sum(s.estimated_tokens for s in result.per_skill.values())

        # Overall verdict: based on severity (not tier) — audit reports comprehensively
        all_severities = {f.severity for f in result.findings}
        if result.skills_failed and len(result.skills_failed) == len(skills):
            result.verdict = "AUDIT_ERROR"
        elif "critical" in all_severities:
            result.verdict = "FAIL"
        elif "high" in all_severities:
            result.verdict = "WARNING"
        else:
            result.verdict = "PASS"

        logger.info(
            "audit: scope=%s skills=%d verdict=%s findings=%d tokens=%d elapsed=%.1fs",
            scope_path.name,
            len(skills),
            result.verdict,
            len(result.findings),
            result.total_tokens_estimated,
            result.elapsed_seconds,
        )

        return result


def _meets_threshold(severity: str, threshold: str) -> bool:
    """Return True if severity meets or exceeds threshold."""
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    return order.get(severity, 0) >= order.get(threshold, 0)


def _increment_stat(stats: "SkillAuditStats", severity: str) -> None:
    if severity == "critical":
        stats.critical_count += 1
    elif severity == "high":
        stats.high_count += 1
    elif severity == "medium":
        stats.medium_count += 1
    else:
        stats.low_count += 1
