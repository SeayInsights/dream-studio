"""Rules-scanner skill-specific checks — hand-coded important rules.

These implement the known important rules for skills that matter most for
the proving run (arch-004, ops-001, pl-009, pl-011, pl-012, etc.)

Split out of rules_scanner.py (WO-GF-CORE-HEALTH-SKILLS): consumed by
rules_scanner_core.py's ``RulesScanner.scan``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .rules_scanner_shared import _SKILL_MODES_ROOT, logger


def _run_skill_specific_checks(
    skill_id: str, scope_path: Path, files: list[Path], context: dict | None = None
) -> list[dict[str, Any]]:
    """Run hand-coded important checks for specific skills."""
    if skill_id == "architecture":
        return _check_architecture(scope_path, files)
    if skill_id == "ops":
        return _check_ops(scope_path, files)
    if skill_id == "pre-launch":
        return _check_pre_launch(scope_path, context)
    if skill_id == "testing":
        return _check_testing(scope_path, files)
    if skill_id == "types-deps":
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
                    window = content.splitlines()[i : i + 3]  # noqa: E203
                    if not any("timeout" in ln for ln in window):
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


def _check_pre_launch(scope_path: Path, context: dict | None = None) -> list[dict[str, Any]]:
    """Key pre-launch checks: legal docs, CHANGELOG, semver tags, runbook, rollback."""
    findings: list[dict[str, Any]] = []

    # Use override from context (set by .launch() with explicit service_type) or infer
    if context and context.get("service_type_override"):
        service_type = context["service_type_override"]
    else:
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

    # pl-009: non-semver tags (also fires when no tags — no versioning established)
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
            if not recent_tags:
                findings.append(
                    {
                        "rule_id": "pl-009",
                        "severity": "high",
                        "tier": "T1",
                        "file_path": ".git/refs/tags",
                        "line": 0,
                        "excerpt": "no tags",
                        "explanation": "No release tags found — semver versioning not established",
                    }
                )
            else:
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
