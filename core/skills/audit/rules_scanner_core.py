"""RulesScanner — parses a skill's rules.yml and applies static detection to files.

Token estimation is accurate enough for the roadmap exit criterion
"token budget measured + validated" without requiring API keys.

Split out of rules_scanner.py (WO-GF-CORE-HEALTH-SKILLS): the RulesScanner
class plus its code-pattern-extraction and severity-mapping utilities.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .rules_scanner_checks import _is_handled_by_specific_check, _run_skill_specific_checks
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


class RulesScanner:
    """Parses a skill's rules.yml and applies static detection to files."""

    def __init__(self, skill_id: str) -> None:
        self.skill_id = skill_id
        self._skill_dir = _SKILL_MODES_ROOT / skill_id
        self._rules: list[dict[str, Any]] = []
        self._file_patterns: tuple[str, ...] = ()
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        rules_path = self._skill_dir / "rules.yml"
        if not rules_path.exists():
            logger.warning("No rules.yml for skill %s at %s", self.skill_id, rules_path)
            self._loaded = True
            return

        try:
            data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
            self._rules = data.get("rules", [])
        except Exception as exc:
            logger.error("Failed to load rules.yml for %s: %s", self.skill_id, exc)

        # Collect file patterns from all rules' applies_to
        patterns: set[str] = set()
        langs: set[str] = set()
        for rule in self._rules:
            applies = rule.get("applies_to", {})
            for ext in applies.get("file_types", []):
                if ext.startswith("."):
                    patterns.add(f"*{ext}")
            for lang in applies.get("languages", []):
                if lang in _LANG_PATTERNS:
                    langs.add(lang)
        # Language patterns as fallback
        for lang in langs:
            patterns.update(_LANG_PATTERNS[lang])

        self._file_patterns = tuple(patterns) or ("*.py",)
        self._loaded = True

    def _iter_files(self, scope_path: Path) -> list[Path]:
        self._load()
        results: list[Path] = []
        for pattern in self._file_patterns:
            for f in scope_path.rglob(pattern):
                if any(part in _SKIP_DIRS for part in f.parts):
                    continue
                results.append(f)
        return sorted(set(results))

    def _static_check_rule(
        self, rule: dict, content: str, file_path: Path, scope_path: Path
    ) -> list[dict[str, Any]]:
        """Apply static detection for a single rule against file content."""
        findings: list[dict[str, Any]] = []
        rule_id = rule.get("id", "")
        severity = rule.get("severity", "medium")
        triggers = rule.get("triggers", [])

        # Skip rules without triggers (can't do static check without patterns)
        if not triggers:
            return findings

        # Use triggers as simple keyword/pattern signals
        for trigger in triggers:
            matched = False
            # Try to extract a code pattern from trigger text
            # E.g. "Route handler accesses request body without schema validation"
            # → look for common patterns in the notes
            static_notes = rule.get("detection", {}).get("static", {}).get("notes", "")

            # Extract Python-like code patterns from static notes
            code_patterns = _extract_code_patterns(static_notes, rule_id)
            for pattern_str, pattern_re in code_patterns:
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    if pattern_re.search(line):
                        findings.append(
                            {
                                "rule_id": rule_id,
                                "severity": severity,
                                "tier": _severity_to_tier(severity, self.skill_id),
                                "file_path": str(file_path.relative_to(scope_path)),
                                "line": i + 1,
                                "excerpt": line.strip()[:80],
                                "explanation": f"[{rule_id}] {trigger}: {pattern_str}",
                            }
                        )
                        matched = True
                        break
                if matched:
                    break

        return findings

    def scan(self, scope_path: Path, context: dict[str, Any]) -> SkillScanResult:
        """Run static scan of scope_path for all static/hybrid rules in this skill."""
        self._load()
        result = SkillScanResult(skill_id=self.skill_id)

        files = self._iter_files(scope_path)
        result.files_scanned = len(files)

        # Skill-specific scanners for known important rules
        skill_findings = _run_skill_specific_checks(self.skill_id, scope_path, files, context)
        result.findings.extend(skill_findings)

        # Generic rules.yml scanner for remaining rules
        for rule in self._rules:
            det = rule.get("detection", {})
            det_type = det.get("type", "static")
            rule_id = rule.get("id", "")

            # Skip rules already handled by skill-specific checks
            if _is_handled_by_specific_check(rule_id, self.skill_id):
                continue

            if det_type in ("static", "hybrid"):
                for file_path in files:
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        rule_findings = self._static_check_rule(
                            rule, content, file_path, scope_path
                        )
                        result.findings.extend(rule_findings)
                    except Exception as exc:
                        logger.debug("scan error on %s rule %s: %s", file_path, rule_id, exc)
                        result.files_skipped += 1

            elif det_type == "llm_only":
                # Record as pending LLM — estimate tokens
                for file_path in files[:10]:  # Sample first 10 files for estimation
                    try:
                        size = file_path.stat().st_size
                        estimated = _BASE_PROMPT_TOKENS + (size // _CHARS_PER_TOKEN)
                        result.llm_pending.append(
                            LLMPendingItem(
                                rule_id=rule_id,
                                skill_id=self.skill_id,
                                severity=rule.get("severity", "medium"),
                                file_path=str(file_path.relative_to(scope_path)),
                                estimated_tokens=estimated,
                            )
                        )
                    except Exception:
                        pass

        return result


# ── Utilities ─────────────────────────────────────────────────────────────


def _extract_code_patterns(notes: str, rule_id: str) -> list[tuple[str, re.Pattern]]:
    """Extract regex patterns from static detection notes text."""
    patterns: list[tuple[str, re.Pattern]] = []
    if not notes:
        return patterns

    # Look for code-like patterns after → arrows, CANDIDATE, FIRE markers
    lines = notes.splitlines()
    for line in lines:
        # Patterns like: `f"...{` → CANDIDATE
        m = re.search(r"[`']([^`']{3,50})[`'].*(?:→|CANDIDATE|FIRE|BLOCK)", line)
        if m:
            raw = m.group(1)
            # Build a simple regex from the pattern
            try:
                # Escape most chars but keep key Python/SQL syntax
                escaped = re.escape(raw).replace(r"\.", ".")
                patterns.append((raw, re.compile(escaped, re.IGNORECASE)))
            except re.error:
                pass

    return patterns[:3]  # limit to 3 patterns per rule to avoid false-positives


def _severity_to_tier(severity: str, skill_id: str) -> str:
    """Map severity to T1/T2/T3 tier for the given skill (audit-mode)."""
    escalated = {"security", "database", "database-compliance"}
    if severity == "critical":
        return "T1"
    if severity == "high":
        return "T1" if skill_id in escalated else "T2"
    if severity == "medium":
        return "T2"
    return "T3"
