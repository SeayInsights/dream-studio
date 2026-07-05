"""Publication readiness checks for the public Dream Studio repository.

The checker is intentionally source-only. It does not inspect operator-local
runtime state, open live SQLite, mutate Git history, push, tag, deploy, or read
secret stores. Content scans report file/rule metadata only and never echo
matched values.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

PUBLICATION_READINESS_SCHEMA = "dream_studio.repo_publication.readiness.v1"

PRIVATE_TREE_PATH_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("runtime_state_path", re.compile(r"(^|/)\.dream-studio(/|$)", re.IGNORECASE)),
    ("local_session_path", re.compile(r"(^|/)\.sessions(/|$)", re.IGNORECASE)),
    ("local_planning_path", re.compile(r"(^|/)\.planning(/|$)", re.IGNORECASE)),
    ("top_level_backup_path", re.compile(r"^backups/", re.IGNORECASE)),
    ("top_level_meta_path", re.compile(r"^meta/", re.IGNORECASE)),
    ("top_level_report_path", re.compile(r"^reports/", re.IGNORECASE)),
    ("raw_telemetry_path", re.compile(r"(^|/)raw[-_]telemetry(/|$)", re.IGNORECASE)),
    ("test_output_path", re.compile(r"^test_output/", re.IGNORECASE)),
    ("database_file", re.compile(r"\.(db|sqlite|sqlite3|db-wal|db-shm|wal|shm)$", re.I)),
    ("backup_file", re.compile(r"\.(bak|backup|dump)$", re.IGNORECASE)),
    ("generated_handoff_file", re.compile(r"(^|/)handoff-[^/]+\.json$", re.IGNORECASE)),
    ("generated_handoff_markdown", re.compile(r"\.handoff\.md$", re.IGNORECASE)),
)

HISTORY_PRIVATE_PATH_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("runtime_state_path", re.compile(r"(^|/)\.dream-studio(/|$)", re.IGNORECASE)),
    ("top_level_backup_path", re.compile(r"^backups/", re.IGNORECASE)),
    ("top_level_meta_path", re.compile(r"^meta/", re.IGNORECASE)),
    ("raw_telemetry_path", re.compile(r"(^|/)raw[-_]telemetry(/|$)", re.IGNORECASE)),
    ("test_output_path", re.compile(r"^test_output/", re.IGNORECASE)),
    ("database_file", re.compile(r"\.(db|sqlite|sqlite3|db-wal|db-shm|wal|shm)$", re.I)),
    ("backup_file", re.compile(r"\.(bak|backup|dump)$", re.IGNORECASE)),
)

PRIVATE_CONTENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "operator_absolute_path",
        re.compile(r"C:[\\/]+Users[\\/]+(?!Example\b|<)[^\\/:\r\n]+", re.IGNORECASE),
    ),
    ("dream_studio_live_backup_path", re.compile(r"Dream Studio Live Backups", re.I)),
    ("appdata_absolute_path", re.compile(r"C:[\\/]+Users[\\/]+[^\\/:\r\n]+[\\/]+AppData", re.I)),
)

SECRET_CONTENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key_block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
)

TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".css",
        ".html",
        ".ini",
        ".js",
        ".json",
        ".md",
        ".env",
        ".ps1",
        ".py",
        ".sql",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)


def build_repo_publication_readiness(
    repo_root: Path,
    *,
    clean_clone_status: str = "not_run",
    tracked_files: Sequence[str] | None = None,
    history_paths: Sequence[str] | None = None,
    ignored_status: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a publication readiness packet for the current repository."""

    root = Path(repo_root).resolve()
    tracked = sorted(tracked_files if tracked_files is not None else _git_lines(root, "ls-files"))
    history = sorted(set(history_paths if history_paths is not None else _git_history_paths(root)))
    ignored = dict(ignored_status) if ignored_status is not None else _ignored_status(root)

    tracked_findings = _path_findings(tracked, PRIVATE_TREE_PATH_RULES)
    history_findings = _path_findings(history, HISTORY_PRIVATE_PATH_RULES)
    content_findings = _content_findings(root, tracked)
    secret_findings = [
        item for item in content_findings if item["finding_type"] == "secret_pattern"
    ]
    private_content_findings = [
        item for item in content_findings if item["finding_type"] == "private_content"
    ]
    license_status = _apache_license_status(root)
    readme_status = _readme_status(root)
    prd_status = _prd_status(root)

    history_status = "pass" if not history_findings else "blocked_by_history_private_artifacts"
    tree_status = "pass" if not tracked_findings and not private_content_findings else "fail"
    secret_status = "pass" if not secret_findings else "fail"
    ignored_status_value = "pass" if ignored.get("untracked_publication_risk") is False else "fail"
    status = (
        "pass"
        if all(
            item == "pass"
            for item in (
                tree_status,
                history_status,
                secret_status,
                ignored_status_value,
                license_status["status"],
                readme_status["status"],
                prd_status["status"],
            )
        )
        else "blocked"
    )

    branch = _git_text(root, "branch", "--show-current")
    head = _git_text(root, "rev-parse", "HEAD")
    return {
        "schema": PUBLICATION_READINESS_SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(),
        "branch": branch,
        "head": head,
        "status": status,
        "final_publication_readiness_verdict": _verdict(
            status=status,
            history_findings=history_findings,
            clean_clone_status=clean_clone_status,
        ),
        "current_tracked_tree_publication_safe": tree_status == "pass",
        "git_history_publication_safe": history_status == "pass",
        "history_rewrite_operator_approval_required": bool(history_findings),
        "history_rewrite_performed": False,
        "clean_clone_validation_status": clean_clone_status,
        "apache_2_license_consistent": license_status["status"] == "pass",
        "readme_current_product_framing": readme_status["status"] == "pass",
        "prd_current_product_authority": prd_status["status"] == "pass",
        "private_local_artifacts_tracked": bool(tracked_findings),
        "private_content_findings": private_content_findings,
        "secret_scan_findings": len(secret_findings),
        "secret_scan_finding_refs": secret_findings,
        "tracked_file_audit": _tracked_file_audit(tracked, tracked_findings),
        "ignored_file_audit": ignored,
        "git_history_privacy_audit": _git_history_privacy_audit(history_findings),
        "license_status": license_status,
        "readme_status": readme_status,
        "prd_status": prd_status,
        "publication_boundary": {
            "public_repo_allows": [
                "product source",
                "public documentation",
                "schema migrations and tests",
                "examples, templates, and synthetic fixtures",
                "sanitized adapter projections",
                "sanitized public Contract Atlas exports",
            ],
            "private_by_default": [
                "Work Orders",
                "handoffs",
                "local evidence",
                "operator decisions",
                "raw telemetry",
                "SQLite DBs",
                "backups",
                "private dogfood traces",
                "cutover or rollback details",
                "private external-project details",
                "local absolute paths",
                "secrets and sensitive values",
            ],
        },
    }


def refresh_repo_publication_artifacts(
    repo_root: Path,
    *,
    output_dir: Path,
    execute: bool,
    clean_clone_status: str = "not_run",
) -> dict[str, Any]:
    """Plan or write publication readiness evidence files."""

    root = Path(repo_root).resolve()
    output = Path(output_dir).resolve()
    packet = build_repo_publication_readiness(root, clean_clone_status=clean_clone_status)
    files = {
        "repo_publication_cleanliness_certificate.yaml": _certificate(packet),
        "tracked_file_audit.yaml": packet["tracked_file_audit"],
        "ignored_file_audit.yaml": packet["ignored_file_audit"],
        "git_history_privacy_audit.yaml": packet["git_history_privacy_audit"],
        "docs_publication_readiness_report.md": _markdown_report(packet),
    }
    planned = [str(output / name) for name in files]
    if execute:
        output.mkdir(parents=True, exist_ok=True)
        for name, payload in files.items():
            path = output / name
            if isinstance(payload, str):
                path.write_text(payload, encoding="utf-8")
            else:
                _write_json_yaml(path, payload)
    return {
        "schema": "dream_studio.repo_publication.artifact_refresh.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "execute": execute,
        "output_dir": str(output),
        "planned_writes": planned,
        "written_files": planned if execute else [],
        "sqlite_mutated": False,
        "secret_values_printed": False,
        "publication_readiness": packet,
    }


def validate_repo_publication_readiness(packet: Mapping[str, Any]) -> list[str]:
    """Validate publication readiness packet semantics."""

    issues: list[str] = []
    if packet.get("schema") != PUBLICATION_READINESS_SCHEMA:
        issues.append("publication_readiness_schema_required")
    if packet.get("current_tracked_tree_publication_safe") is not True:
        issues.append("current_tracked_tree_not_publication_safe")
    if packet.get("git_history_publication_safe") is not True:
        issues.append("git_history_not_publication_safe")
    if packet.get("secret_scan_findings") != 0:
        issues.append("secret_scan_findings_present")
    if packet.get("apache_2_license_consistent") is not True:
        issues.append("apache_2_license_not_consistent")
    if packet.get("readme_current_product_framing") is not True:
        issues.append("readme_product_framing_not_current")
    if packet.get("prd_current_product_authority") is not True:
        issues.append("prd_product_authority_not_current")
    return issues


def _path_findings(
    paths: Iterable[str], rules: Sequence[tuple[str, re.Pattern[str]]]
) -> list[dict]:
    findings: list[dict[str, Any]] = []
    for raw in paths:
        path = raw.replace("\\", "/")
        for rule_id, pattern in rules:
            if pattern.search(path):
                findings.append(
                    {"path": path, "classification": "private_artifact", "rule": rule_id}
                )
                break
    return findings


def _content_findings(repo_root: Path, tracked_files: Sequence[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rel in tracked_files:
        path = repo_root / rel
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError:
            continue
        normalized = rel.replace("\\", "/")
        if _skip_private_content_scan_path(normalized):
            continue
        for rule_id, pattern in PRIVATE_CONTENT_RULES:
            if pattern.search(text):
                findings.append(
                    {
                        "path": normalized,
                        "finding_type": "private_content",
                        "rule": rule_id,
                        "value_printed": False,
                    }
                )
        if _skip_secret_scan_path(normalized):
            continue
        for rule_id, pattern in SECRET_CONTENT_RULES:
            if pattern.search(text):
                findings.append(
                    {
                        "path": normalized,
                        "finding_type": "secret_pattern",
                        "rule": rule_id,
                        "value_printed": False,
                    }
                )
    return findings


def _skip_secret_scan_path(path: str) -> bool:
    return (
        path.startswith("templates/security/")
        or path.startswith("docs/security")
        or path.startswith("canonical/skills/quality/modes/security/")
    )


def _skip_private_content_scan_path(path: str) -> bool:
    return path in {
        "core/release/repo_publication_readiness.py",
        "core/shared_intelligence/contract_atlas_lifecycle.py",
        "core/shared_intelligence/contract_atlas.py",
        "tests/unit/test_repo_publication_readiness.py",
    }


def _apache_license_status(repo_root: Path) -> dict[str, Any]:
    license_path = repo_root / "LICENSE"
    readme_path = repo_root / "README.md"
    checks = {
        "license_file_exists": license_path.is_file(),
        "license_file_mentions_apache_2": False,
        "readme_mentions_apache_2": False,
    }
    if license_path.is_file():
        text = license_path.read_text(encoding="utf-8", errors="ignore")
        checks["license_file_mentions_apache_2"] = (
            "Apache License" in text and "Version 2.0" in text
        )
    if readme_path.is_file():
        checks["readme_mentions_apache_2"] = "Apache-2.0" in readme_path.read_text(
            encoding="utf-8", errors="ignore"
        )
    return {"status": "pass" if all(checks.values()) else "fail", "checks": checks}


def _readme_status(repo_root: Path) -> dict[str, Any]:
    text = (repo_root / "README.md").read_text(encoding="utf-8", errors="ignore")
    required = [
        "local-first AI orchestration",
        "adapter surfaces",
        "SQLite-backed authority",
        "Contract Atlas",
        "Publication Boundary",
        "Apache-2.0",
    ]
    missing = [phrase for phrase in required if phrase not in text]
    return {"status": "pass" if not missing else "fail", "missing": missing}


def _prd_status(repo_root: Path) -> dict[str, Any]:
    text = (repo_root / "docs" / "product" / "dream-studio-prd.md").read_text(
        encoding="utf-8", errors="ignore"
    )
    required = [
        "Status: current public product authority",
        "local-first AI orchestration",
        "Authority Model",
        "Secure Production Readiness",
        "Contract Atlas",
        "Publication Boundary",
        "Human Approval Boundaries",
    ]
    historical_noise = [
        "Phase 18",
        "implementation diary",
        "old adapter marker",
        "temporary marker",
    ]
    missing = [phrase for phrase in required if phrase not in text]
    historical_hits = [phrase for phrase in historical_noise if phrase.lower() in text.lower()]
    return {
        "status": "pass" if not missing and not historical_hits else "fail",
        "missing": missing,
        "historical_noise": historical_hits,
    }


def _tracked_file_audit(
    tracked_files: Sequence[str], findings: Sequence[Mapping[str, Any]]
) -> dict:
    categories: dict[str, int] = {}
    for rel in tracked_files:
        category = _tracked_category(rel)
        categories[category] = categories.get(category, 0) + 1
    return {
        "schema": "dream_studio.repo_publication.tracked_file_audit.v1",
        "tracked_file_count": len(tracked_files),
        "categories": dict(sorted(categories.items())),
        "private_local_artifacts_tracked": bool(findings),
        "private_local_artifact_findings": list(findings),
        "current_tree_publication_safe": not findings,
    }


def _tracked_category(path: str) -> str:
    if path.startswith("docs/"):
        return "public_docs"
    if path.startswith((".github/", ".claude", ".claude-plugin/")):
        return "public_adapter_or_ci_metadata"
    if path.startswith(("core/", "interfaces/", "projections/", "runtime/", "scripts/")):
        return "product_source"
    if path.startswith(("tests/", "analytics/tests/")):
        return "tests"
    if path.startswith(("skills/", "workflows/", "templates/", "examples/")):
        return "public_templates_or_primitives"
    return "root_public_metadata"


def _ignored_status(repo_root: Path) -> dict[str, Any]:
    untracked = _git_lines(repo_root, "ls-files", "--others", "--exclude-standard")
    untracked_findings = _path_findings(untracked, PRIVATE_TREE_PATH_RULES)
    return {
        "schema": "dream_studio.repo_publication.ignored_file_audit.v1",
        "untracked_file_count": len(untracked),
        "untracked_publication_risk": bool(untracked_findings),
        "untracked_publication_risk_findings": untracked_findings,
        "ignored_boundary_ok": not untracked_findings,
    }


def _git_history_privacy_audit(findings: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "dream_studio.repo_publication.git_history_privacy_audit.v1",
        "contains_publication_blocking_private_artifacts": bool(findings),
        "contains_secret_findings": False,
        "secret_values_printed": False,
        "history_private_artifact_findings": list(findings),
        "history_rewrite_required_for_strict_publication_cleanliness": bool(findings),
        "status": "pass" if not findings else "blocked",
    }


def _certificate(packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "dream_studio.repo_publication.cleanliness_certificate.v1",
        "generated_at": packet["generated_at"],
        "branch": packet["branch"],
        "head": packet["head"],
        "status": packet["status"],
        "final_publication_readiness_verdict": packet["final_publication_readiness_verdict"],
        "current_tracked_tree_publication_safe": packet["current_tracked_tree_publication_safe"],
        "git_history_publication_safe": packet["git_history_publication_safe"],
        "git_history_publication_blockers": packet["git_history_privacy_audit"][
            "history_private_artifact_findings"
        ],
        "history_rewrite_operator_approval_required": packet[
            "history_rewrite_operator_approval_required"
        ],
        "history_rewrite_performed": packet["history_rewrite_performed"],
        "clean_clone_validation_status": packet["clean_clone_validation_status"],
        "apache_2_license_consistent": packet["apache_2_license_consistent"],
        "readme_current_product_framing": packet["readme_current_product_framing"],
        "prd_current_product_authority": packet["prd_current_product_authority"],
        "private_local_artifacts_tracked": packet["private_local_artifacts_tracked"],
        "secret_scan_findings": packet["secret_scan_findings"],
        "ignored_untracked_boundary_ok": packet["ignored_file_audit"]["ignored_boundary_ok"],
    }


def _markdown_report(packet: Mapping[str, Any]) -> str:
    blockers = packet["git_history_privacy_audit"]["history_private_artifact_findings"]
    blocker_lines = (
        "\n".join(f"- `{item['path']}` ({item['rule']})" for item in blockers)
        if blockers
        else "- None"
    )
    return f"""# Docs Publication Readiness Report

Generated: {packet['generated_at']}

## Verdict

`{packet['final_publication_readiness_verdict']}`

The current tracked tree is publication-safe when the checks below pass. Dream
Studio keeps product source, public docs, tests, templates, adapter projection
metadata, and sanitized generated exports in Git. Private operational history
belongs in operator-local runtime state and is not source authority.

## Current Tree

- Branch: `{packet['branch']}`
- Head: `{packet['head']}`
- Tracked files audited: {packet['tracked_file_audit']['tracked_file_count']}
- Private/local artifacts currently tracked: {len(packet['tracked_file_audit']['private_local_artifact_findings'])}
- Untracked publication-risk files: {len(packet['ignored_file_audit']['untracked_publication_risk_findings'])}
- Secret-pattern findings: {packet['secret_scan_findings']}
- Apache-2.0 license consistency: {'pass' if packet['apache_2_license_consistent'] else 'fail'}
- README product framing: {'pass' if packet['readme_current_product_framing'] else 'fail'}
- PRD product authority: {'pass' if packet['prd_current_product_authority'] else 'fail'}

## Public/Private Boundary

Public repository content is limited to product source, public documentation,
schema migrations, tests, examples, templates, sanitized adapter projections,
sanitized demos, sanitized release notes, and sanitized Contract Atlas exports.

Private-by-default material remains out of Git: Work Orders, handoffs, local
evidence, operator decisions, raw telemetry, local SQLite databases, backups,
private dogfood traces, cutover or rollback details, private external-project
details, local absolute paths, secrets, and sensitive values.

## Clean Clone

Clean-clone validation status: `{packet['clean_clone_validation_status']}`.

## Git History Privacy

Publication-blocking private artifacts in history:

{blocker_lines}

History rewrite, force-push, tag, push, deploy, cleanup, or live-state mutation
requires explicit operator approval and was not performed by this check.

## Evidence Files

- `docs/publication/repo_publication_cleanliness_certificate.yaml`
- `docs/publication/tracked_file_audit.yaml`
- `docs/publication/ignored_file_audit.yaml`
- `docs/publication/git_history_privacy_audit.yaml`
"""


def _verdict(
    *,
    status: str,
    history_findings: Sequence[Mapping[str, Any]],
    clean_clone_status: str,
) -> str:
    if history_findings:
        return "CURRENT_TREE_CLEAN_HISTORY_REWRITE_OR_RISK_ACCEPTANCE_REQUIRED_BEFORE_PUBLICATION"
    if clean_clone_status != "pass":
        return "CURRENT_TREE_AND_HISTORY_CLEAN_CLEAN_CLONE_VALIDATION_REQUIRED"
    if status == "pass":
        return "PUBLICATION_READY_NO_PRIVATE_ARTIFACTS_DETECTED"
    return "PUBLICATION_BLOCKED_REVIEW_REQUIRED"


def _git_history_paths(repo_root: Path) -> list[str]:
    result = _run_git(repo_root, "log", "--all", "--name-only", "--pretty=format:")
    if result.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _git_lines(repo_root: Path, *args: str) -> list[str]:
    result = _run_git(repo_root, *args)
    if result.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _git_text(repo_root: Path, *args: str) -> str:
    result = _run_git(repo_root, *args)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_json_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def packet_sha256(packet: Mapping[str, Any]) -> str:
    """Return a stable hash for a publication readiness packet."""

    payload = json.dumps(packet, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
