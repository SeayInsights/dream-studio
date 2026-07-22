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

Split out of dispatcher.py (WO-GF-CORE-HEALTH-SKILLS): the class body only;
constants live in dispatcher_shared.py and result/finding dataclasses live in
dispatcher_models.py.
"""

from __future__ import annotations

import concurrent.futures
import time
from pathlib import Path
from typing import Any

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
            if skill == "security":
                from core.skills.build.security import audit_generated_python

                return audit_generated_python(code_artifact, context)
            if skill == "database":
                from core.skills.build.database import audit_generated_sql_or_python

                return audit_generated_sql_or_python(code_artifact, context)
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
        _extra_context: dict | None = None,
    ) -> AuditResult:
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

        scope_path = Path(scope_path)
        context: dict[str, Any] = {
            "scope_path": str(scope_path),
            "language_filter": language_filter,
        }
        if _extra_context:
            context.update(_extra_context)

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
        # Phase 19.7: snapshot active personalization overrides at dispatch start.
        # Snapshot is taken BEFORE spawning threads so all threads use the same set.
        # Mid-audit state changes don't affect the running audit (session isolation).
        try:
            from core.expansion.loader import ExtensionLoader

            _ext_snapshot = ExtensionLoader().snapshot(skills)
        except Exception:
            _ext_snapshot = {}

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
                    # Phase 19.7: apply personalization overrides from snapshot
                    if _ext_snapshot.get(skill_id):
                        try:
                            from core.expansion.loader import apply_personalization_overrides

                            raw_findings = apply_personalization_overrides(
                                raw_findings, _ext_snapshot[skill_id]
                            )
                        except Exception:
                            pass
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
                    # Phase 19.7: apply personalization overrides from snapshot
                    if _ext_snapshot.get(skill_id):
                        try:
                            from core.expansion.loader import apply_personalization_overrides

                            scan_res.findings = apply_personalization_overrides(
                                scan_res.findings, _ext_snapshot[skill_id]
                            )
                        except Exception:
                            pass
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

    # ── .launch() ──────────────────────────────────────────────────────────

    @classmethod
    def launch(
        cls,
        scope_path: Path,
        service_type: str | None = None,
    ) -> LaunchResult:
        """Run launch-gate audit — .audit() + service-type-aware escalation.

        Reads escalation map from pre-launch skill config.yml (source of truth).
        Returns LAUNCH_READY / LAUNCH_WARNING / LAUNCH_BLOCKED verdict.

        Args:
            scope_path: Absolute path to repository root.
            service_type: Explicit override: 'consumer' | 'developer-tool' |
                'internal-service' | 'library'. None = auto-infer.

        Returns:
            LaunchResult with verdict, service_type, full audit_result,
            blocking and warning finding lists, and human-readable summary.
        """
        import yaml

        scope_path = Path(scope_path)
        start = time.monotonic()

        # ── 1. Resolve service_type ────────────────────────────────────────
        if service_type is None:
            from core.skills.audit.rules_scanner import _infer_service_type

            service_type = _infer_service_type(scope_path)

        # ── 2. Load escalation map from pre-launch config.yml ─────────────
        _SKILL_MODES = Path(__file__).parents[2] / "canonical" / "skills" / "quality" / "modes"
        config_path = _SKILL_MODES / "pre-launch" / "config.yml"
        escalation: dict = {}
        try:
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            escalation = cfg.get("launch_escalation", {}).get(service_type, {})
        except Exception as exc:
            logger.warning("Could not load launch escalation config: %s", exc)

        blocked_rules: set[str] = set(escalation.get("blocked_rules", []))
        warning_rules: set[str] = set(escalation.get("warning_rules", []))
        silent_rules: set[str] = set(escalation.get("silent_rules", []))
        blocked_severities: set[str] = set(escalation.get("blocked_severities", ["critical"]))

        # ── 3. Run full audit — pass service_type override so pre-launch scanner uses it
        audit_result = cls.audit(
            scope_path,
            _extra_context={"service_type_override": service_type},
        )

        # ── 4. Apply escalation to produce launch verdict ─────────────────
        blocking: list[AuditFinding] = []
        warning: list[AuditFinding] = []

        for finding in audit_result.findings:
            rule_id = finding.rule_id
            severity = finding.severity

            # Silent rules are excluded from launch verdict
            if rule_id in silent_rules:
                continue

            # Blocked by explicit rule list or severity
            if rule_id in blocked_rules or severity in blocked_severities:
                blocking.append(finding)
            elif rule_id in warning_rules:
                warning.append(finding)
            # else: audit-level pass — doesn't affect launch verdict

        # ── 5. Determine verdict ───────────────────────────────────────────
        if blocking:
            verdict = "LAUNCH_BLOCKED"
        elif warning:
            verdict = "LAUNCH_WARNING"
        else:
            verdict = "LAUNCH_READY"

        elapsed = time.monotonic() - start

        # ── 6. Build summary ───────────────────────────────────────────────
        summary_lines = [
            f"Launch Gate — {scope_path.name} (service_type: {service_type})",
            f"Verdict: {verdict}",
        ]
        if blocking:
            summary_lines.append(f"\nBlocking ({len(blocking)}):")
            for f in blocking[:10]:
                summary_lines.append(f"  [{f.rule_id}] {f.skill_id}: {f.explanation[:60]}")
            if len(blocking) > 10:
                summary_lines.append(f"  ... and {len(blocking) - 10} more")
        if warning:
            summary_lines.append(f"\nWarnings ({len(warning)}):")
            for f in warning[:5]:
                summary_lines.append(f"  [{f.rule_id}] {f.skill_id}: {f.explanation[:60]}")

        logger.info(
            "launch: scope=%s service_type=%s verdict=%s blocking=%d warnings=%d elapsed=%.1fs",
            scope_path.name,
            service_type,
            verdict,
            len(blocking),
            len(warning),
            elapsed,
        )

        return LaunchResult(
            verdict=verdict,
            service_type=service_type,
            audit_result=audit_result,
            blocking_findings=blocking,
            warning_findings=warning,
            launch_summary="\n".join(summary_lines),
            elapsed_seconds=elapsed,
            tokens_consumed=audit_result.total_tokens_estimated,
        )
