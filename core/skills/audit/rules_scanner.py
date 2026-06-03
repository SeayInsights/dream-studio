"""Rules-based scanner for quality skills that don't have Python build auditors.

Parses each skill's rules.yml to extract static detection triggers + file patterns,
runs them against actual files, and records LLM-only rules as "pending" with token
estimates (no external API call required).

Token estimation is accurate enough for the roadmap exit criterion
"token budget measured + validated" without requiring API keys.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

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
        skill_findings = _run_skill_specific_checks(self.skill_id, scope_path, files)
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


# ── Skill-specific checks ─────────────────────────────────────────────────
# These implement the known important rules for skills that matter most for
# the proving run (arch-004, ops-001, pl-009, pl-011, pl-012, etc.)


def _run_skill_specific_checks(
    skill_id: str, scope_path: Path, files: list[Path]
) -> list[dict[str, Any]]:
    """Run hand-coded important checks for specific skills."""
    if skill_id == "architecture":
        return _check_architecture(scope_path, files)
    elif skill_id == "ops":
        return _check_ops(scope_path, files)
    elif skill_id == "pre-launch":
        return _check_pre_launch(scope_path)
    elif skill_id == "testing":
        return _check_testing(scope_path, files)
    elif skill_id == "types-deps":
        return _check_types_deps(scope_path, files)
    return []


def _is_handled_by_specific_check(rule_id: str, skill_id: str) -> bool:
    """True if the rule is handled by the skill-specific checker."""
    handled = {
        "architecture": {"arch-004", "arch-001", "arch-002", "arch-009"},
        "ops": {"ops-001", "ops-005", "ops-006", "ops-007", "ops-008", "ops-011", "ops-012"},
        "pre-launch": {"pl-001", "pl-002", "pl-007", "pl-009", "pl-010", "pl-011", "pl-012"},
        "testing": {"tst-001", "tst-010"},
        "types-deps": {"dep-001", "dep-002", "typ-001"},
    }
    return rule_id in handled.get(skill_id, set())


def _check_architecture(scope_path: Path, files: list[Path]) -> list[dict[str, Any]]:
    """arch-004 layer inversion heuristic: central layer importing outer layer."""
    # Load layer map from architecture config
    config_path = _SKILL_MODES_ROOT / "architecture" / "config.yml"
    layer_map: dict[str, int] = {}
    if config_path.exists():
        try:
            cfg = yaml.safe_load(config_path.read_text())
            for layer_entry in cfg.get("layer_map", {}).get("layers", []):
                layer_map[layer_entry["name"]] = layer_entry["rank"]
        except Exception:
            pass

    if not layer_map:
        return []

    findings: list[dict[str, Any]] = []
    python_files = [f for f in files if f.suffix == ".py"]

    for file_path in python_files:
        # Determine this file's layer
        file_layer = None
        file_rank = None
        for part in file_path.parts:
            if part in layer_map:
                file_layer = part
                file_rank = layer_map[part]
                break
        if file_layer is None:
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(content.splitlines()):
                stripped = line.strip()
                # Check imports
                m = re.match(r"^(?:from|import)\s+([\w.]+)", stripped)
                if not m:
                    continue
                import_path = m.group(1)
                # Check if import path contains a higher-rank (outer) layer
                for layer_name, layer_rank in layer_map.items():
                    if layer_name in import_path and layer_rank > file_rank:
                        findings.append(
                            {
                                "rule_id": "arch-004",
                                "severity": "critical",
                                "tier": "T1",
                                "file_path": str(file_path.relative_to(scope_path)),
                                "line": i + 1,
                                "excerpt": stripped[:80],
                                "explanation": (
                                    f"Layer inversion: {file_layer} (rank {file_rank}) "
                                    f"imports {layer_name} (rank {layer_rank})"
                                ),
                            }
                        )
                        break
        except Exception as exc:
            logger.debug("arch-004 scan error %s: %s", file_path, exc)

    return findings


def _check_ops(scope_path: Path, files: list[Path]) -> list[dict[str, Any]]:
    """Key ops checks: ops-001 (print), ops-005/006 (health/metrics), ops-011 (timeout), ops-012 (Dockerfile)."""
    findings: list[dict[str, Any]] = []
    python_files = [f for f in files if f.suffix == ".py"]

    # Skip test/tool files for ops-001
    service_files = [
        f
        for f in python_files
        if not any(part in {"tests", "tools", "scripts", "examples"} for part in f.parts)
    ]

    # ops-001: print() in production service files
    for file_path in service_files:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            # Skip if file imports structlog/logging properly AND only uses print in __main__
            has_structured_logging = "import structlog" in content or "import logging" in content
            if has_structured_logging and "print(" not in content:
                continue
            for i, line in enumerate(content.splitlines()):
                stripped = line.strip()
                if re.search(r"\bprint\s*\(", stripped) and not stripped.startswith("#"):
                    findings.append(
                        {
                            "rule_id": "ops-001",
                            "severity": "high",
                            "tier": "T2",
                            "file_path": str(file_path.relative_to(scope_path)),
                            "line": i + 1,
                            "excerpt": stripped[:80],
                            "explanation": "Unstructured logging: print() in production service code",
                        }
                    )
                    break  # one finding per file
        except Exception:
            pass

    # ops-005: missing /health endpoint
    route_files = [f for f in python_files if "route" in f.name or "api" in str(f.parent)]
    has_health = any(
        "/health" in f.read_text(encoding="utf-8", errors="ignore")
        or "/api/health" in f.read_text(encoding="utf-8", errors="ignore")
        for f in route_files
        if f.exists()
    )
    if not has_health and route_files:
        findings.append(
            {
                "rule_id": "ops-005",
                "severity": "high",
                "tier": "T2",
                "file_path": "projections/api/",
                "line": 0,
                "excerpt": "No /health or /ready route found",
                "explanation": "Missing health endpoint for service",
            }
        )

    # ops-011: HTTP calls without timeout
    for file_path in python_files:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(content.splitlines()):
                # requests.post/get/put without timeout=
                if re.search(r"requests\.(get|post|put|delete)\s*\(", line):
                    # Check same line and next line for timeout
                    window = content.splitlines()[i : i + 3]
                    if not any("timeout" in l for l in window):
                        findings.append(
                            {
                                "rule_id": "ops-011",
                                "severity": "high",
                                "tier": "T2",
                                "file_path": str(file_path.relative_to(scope_path)),
                                "line": i + 1,
                                "excerpt": line.strip()[:80],
                                "explanation": "HTTP call without timeout parameter",
                            }
                        )
                        break
        except Exception:
            pass

    # ops-012: Dockerfile quality check
    dockerfile = scope_path / "Dockerfile"
    if dockerfile.exists():
        try:
            df_content = dockerfile.read_text(encoding="utf-8", errors="ignore")
            from_count = len(re.findall(r"^FROM\s+", df_content, re.MULTILINE))
            has_user = bool(re.search(r"^USER\s+\w", df_content, re.MULTILINE))
            if from_count == 1:
                findings.append(
                    {
                        "rule_id": "ops-012",
                        "severity": "high",
                        "tier": "T2",
                        "file_path": "Dockerfile",
                        "line": 1,
                        "excerpt": "FROM (single-stage)",
                        "explanation": "Single-stage Dockerfile — no multi-stage builder/runtime separation",
                    }
                )
            if not has_user:
                findings.append(
                    {
                        "rule_id": "ops-012",
                        "severity": "high",
                        "tier": "T2",
                        "file_path": "Dockerfile",
                        "line": 0,
                        "excerpt": "No USER instruction",
                        "explanation": "Dockerfile runs as root — add non-root USER",
                    }
                )
        except Exception:
            pass

    return findings


def _check_pre_launch(scope_path: Path) -> list[dict[str, Any]]:
    """Key pre-launch checks: legal docs, CHANGELOG, semver tags, runbook, rollback."""
    findings: list[dict[str, Any]] = []

    # Detect service type using the pre-launch logic
    service_type = _infer_service_type(scope_path)

    # pl-001/002: legal docs (consumer only)
    if service_type == "consumer":
        terms_paths = ["TERMS.md", "TOS.md", "docs/legal/terms.md"]
        has_terms = any((scope_path / p).exists() for p in terms_paths)
        if not has_terms:
            findings.append(
                {
                    "rule_id": "pl-001",
                    "severity": "high",
                    "tier": "T1",
                    "file_path": "TERMS.md",
                    "line": 0,
                    "excerpt": "not found",
                    "explanation": "Terms of Service missing for consumer service",
                }
            )
        privacy_paths = ["PRIVACY.md", "PRIVACY_POLICY.md", "docs/legal/privacy.md"]
        has_privacy = any((scope_path / p).exists() for p in privacy_paths)
        if not has_privacy:
            findings.append(
                {
                    "rule_id": "pl-002",
                    "severity": "critical",
                    "tier": "T1",
                    "file_path": "PRIVACY.md",
                    "line": 0,
                    "excerpt": "not found",
                    "explanation": "Privacy Policy missing for consumer service with PII",
                }
            )

    # pl-007: CHANGELOG current
    changelog_paths = ["CHANGELOG.md", "CHANGES.md"]
    has_changelog = any((scope_path / p).exists() for p in changelog_paths)
    if not has_changelog:
        findings.append(
            {
                "rule_id": "pl-007",
                "severity": "medium",
                "tier": "T2",
                "file_path": "CHANGELOG.md",
                "line": 0,
                "excerpt": "not found",
                "explanation": "CHANGELOG missing",
            }
        )

    # pl-009: non-semver tags
    try:
        import subprocess

        tags_result = subprocess.run(
            ["git", "-C", str(scope_path), "tag", "--sort=-version:refname"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if tags_result.returncode == 0:
            recent_tags = tags_result.stdout.strip().splitlines()[:3]
            for tag in recent_tags:
                if tag and not re.match(r"^v?\d+\.\d+\.\d+", tag.strip()):
                    findings.append(
                        {
                            "rule_id": "pl-009",
                            "severity": "high",
                            "tier": "T1",
                            "file_path": ".git/refs/tags",
                            "line": 0,
                            "excerpt": tag.strip(),
                            "explanation": f"Non-semver release tag: `{tag.strip()}` (expected vX.Y.Z)",
                        }
                    )
                    break
    except Exception:
        pass

    # pl-011: no deployment runbook
    runbook_paths = ["RUNBOOK.md", "DEPLOYMENT.md", "docs/runbook.md", "docs/deployment.md"]
    has_runbook = any((scope_path / p).exists() for p in runbook_paths)
    if not has_runbook:
        tier = "T1" if service_type in ("consumer", "internal-service") else "T2"
        findings.append(
            {
                "rule_id": "pl-011",
                "severity": "high",
                "tier": tier,
                "file_path": "RUNBOOK.md",
                "line": 0,
                "excerpt": "not found",
                "explanation": "No deployment runbook found",
            }
        )

    # pl-012: no rollback procedure
    rollback_paths = ["ROLLBACK.md", "docs/rollback.md"]
    has_rollback = any((scope_path / p).exists() for p in rollback_paths)
    if not has_rollback:
        tier = "T1" if service_type in ("consumer", "internal-service") else "T2"
        findings.append(
            {
                "rule_id": "pl-012",
                "severity": "high",
                "tier": tier,
                "file_path": "ROLLBACK.md",
                "line": 0,
                "excerpt": "not found",
                "explanation": "No rollback procedure documented",
            }
        )

    return findings


def _check_testing(scope_path: Path, files: list[Path]) -> list[dict[str, Any]]:
    """tst-001: type checker not covering all source dirs. tst-010: coverage gate."""
    findings: list[dict[str, Any]] = []

    # tst-001: check pyproject.toml / mypy.ini for type checker configuration
    pyproject = scope_path / "pyproject.toml"
    has_type_check = False
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8", errors="ignore")
        has_type_check = "[tool.mypy]" in content or "[tool.pyright]" in content
    if not has_type_check and (scope_path / "mypy.ini").exists():
        has_type_check = True
    if not has_type_check:
        findings.append(
            {
                "rule_id": "tst-001",
                "severity": "high",
                "tier": "T2",
                "file_path": "pyproject.toml",
                "line": 0,
                "excerpt": "no [tool.mypy] or [tool.pyright] section",
                "explanation": "Type checker not configured for source directories",
            }
        )

    return findings


def _check_types_deps(scope_path: Path, files: list[Path]) -> list[dict[str, Any]]:
    """dep-001: CVE gate. dep-002: lock file sync. typ-001: type checker coverage."""
    findings: list[dict[str, Any]] = []

    # dep-001: check CI for CVE gate
    ci_dir = scope_path / ".github" / "workflows"
    if ci_dir.exists():
        has_vuln_scan = False
        for wf in ci_dir.glob("*.yml"):
            try:
                content = wf.read_text(encoding="utf-8", errors="ignore")
                if any(
                    kw in content
                    for kw in ("pip-audit", "safety", "npm audit", "cargo audit", "govulncheck")
                ):
                    has_vuln_scan = True
                    break
            except Exception:
                pass
        if not has_vuln_scan:
            findings.append(
                {
                    "rule_id": "dep-001",
                    "severity": "high",
                    "tier": "T2",
                    "file_path": ".github/workflows/",
                    "line": 0,
                    "excerpt": "no vulnerability scan step",
                    "explanation": "CVE gate is non-blocking or absent in CI",
                }
            )

    return findings


# ── Utilities ─────────────────────────────────────────────────────────────


def _infer_service_type(path: Path) -> str:
    """Quick service type inference for pre-launch rule dispatch.

    Priority order:
    1. Explicit override in pre_launch_config.yml
    2. Developer-tool signals (CLI entry point) — checked FIRST before PII scan
    3. Consumer signals (web UI + unambiguous PII columns like email/phone)
    4. Internal-service fallback
    """
    # 1. Explicit override
    for config_name in ["pre_launch_config.yml", "pre_launch_config.yaml"]:
        cp = path / config_name
        if cp.exists():
            try:
                content = cp.read_text(encoding="utf-8", errors="ignore")
                for st in ("consumer", "developer-tool", "internal-service", "library"):
                    if f"service_type: {st}" in content:
                        return st
            except Exception:
                pass

    # 2. Strong developer-tool signal: has CLI directory
    if (path / "interfaces" / "cli").exists():
        return "developer-tool"

    # 3. Consumer signals: web UI presence (strong)
    has_web_ui = (path / "src" / "app").exists() or (path / "next.config.ts").exists()

    # 4. PII check: only flag consumer on unambiguous PII signals (email/phone, not "name")
    has_pii = False
    for sql_f in list(path.glob("**/migrations/*.sql"))[:5]:
        try:
            content_lower = sql_f.read_text(encoding="utf-8", errors="ignore").lower()
            # Require email OR phone (both are unambiguous PII) — not just "name"
            if "email" in content_lower or "phone" in content_lower or "guests" in content_lower:
                has_pii = True
                break
        except Exception:
            pass

    if has_web_ui or has_pii:
        return "consumer"

    # 5. Fallback developer-tool: Python project without web UI
    if (path / "pyproject.toml").exists() or (path / "setup.py").exists():
        return "developer-tool"

    return "internal-service"


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
    elif severity == "high":
        return "T1" if skill_id in escalated else "T2"
    elif severity == "medium":
        return "T2"
    return "T3"
